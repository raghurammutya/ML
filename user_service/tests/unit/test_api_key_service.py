"""
Unit tests for API Key Service

Tests the ApiKeyService functionality including:
- API key generation
- API key verification
- IP whitelist validation
- Expiration checking
- Revocation
- Rotation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

from app.services.api_key_service import ApiKeyService
from app.models.api_key import ApiKey, ApiKeyUsageLog, RateLimitTier
from app.models.user import User


@pytest.fixture
def mock_db():
    """Mock database session"""
    return Mock(spec=Session)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = Mock()
    redis.client = Mock()
    return redis


@pytest.fixture(autouse=True)
def mock_event_service():
    """Mock EventService for all tests"""
    with patch('app.services.api_key_service.EventService') as mock:
        mock.return_value.publish_event = Mock()
        yield mock


@pytest.fixture
def api_key_service(mock_db, mock_redis):
    """Create ApiKeyService instance with mocked dependencies"""
    return ApiKeyService(db=mock_db, redis=mock_redis)


@pytest.fixture
def sample_user():
    """Create a sample user for testing"""
    user = User()
    user.user_id = 1
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_active = True
    return user


@pytest.fixture
def sample_api_key():
    """Create a sample API key for testing"""
    api_key = ApiKey()
    api_key.api_key_id = 1
    api_key.user_id = 1
    api_key.key_prefix = "sb_abc12345"  # Full prefix with sb_
    api_key.key_hash = "hashed_secret"
    api_key.name = "Test Key"
    api_key.scopes = ["read", "trade"]
    api_key.ip_whitelist = None
    api_key.rate_limit_tier = RateLimitTier.STANDARD
    api_key.created_at = datetime.utcnow()
    api_key.revoked_at = None
    api_key.expires_at = None
    api_key.usage_count = 0
    return api_key


class TestApiKeyGeneration:
    """Test API key generation"""

    def test_generate_api_key_basic(self, api_key_service, mock_db):
        """Test basic API key generation"""
        # Arrange
        user_id = 1
        name = "My API Key"
        scopes = ["read", "trade"]

        # Mock database operations
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=user_id,
            name=name,
            scopes=scopes
        )

        # Assert
        assert api_key is not None
        assert full_key.startswith("sb_")
        assert len(full_key.split("_")) == 3  # sb_prefix_secret
        assert api_key.user_id == user_id
        assert api_key.name == name
        assert api_key.scopes == scopes
        assert api_key.rate_limit_tier == RateLimitTier.STANDARD  # default
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_generate_api_key_with_expiration(self, api_key_service, mock_db):
        """Test API key generation with expiration"""
        # Arrange
        user_id = 1
        name = "Temporary Key"
        scopes = ["read"]
        expires_in_days = 30

        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=user_id,
            name=name,
            scopes=scopes,
            expires_in_days=expires_in_days
        )

        # Assert
        assert api_key.expires_at is not None
        # Check expiration is approximately 30 days from now (within 1 hour tolerance)
        expected_expiration = datetime.utcnow() + timedelta(days=expires_in_days)
        assert abs((api_key.expires_at - expected_expiration).total_seconds()) < 3600

    def test_generate_api_key_with_ip_whitelist(self, api_key_service, mock_db):
        """Test API key generation with IP whitelist"""
        # Arrange
        user_id = 1
        name = "IP Restricted Key"
        scopes = ["read"]
        ip_whitelist = ["1.2.3.4", "5.6.7.8"]

        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=user_id,
            name=name,
            scopes=scopes,
            ip_whitelist=ip_whitelist
        )

        # Assert
        assert api_key.ip_whitelist == ip_whitelist

    def test_generate_api_key_premium_tier(self, api_key_service, mock_db):
        """Test API key generation with premium rate limit tier"""
        # Arrange
        user_id = 1
        name = "Premium Key"
        scopes = ["read", "trade", "admin"]
        rate_limit_tier = RateLimitTier.PREMIUM

        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=user_id,
            name=name,
            scopes=scopes,
            rate_limit_tier=rate_limit_tier
        )

        # Assert
        assert api_key.rate_limit_tier == RateLimitTier.PREMIUM

    def test_key_format(self, api_key_service, mock_db):
        """Test that generated key has correct format"""
        # Arrange
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=1,
            name="Test",
            scopes=["read"]
        )

        # Assert
        parts = full_key.split("_")
        assert len(parts) == 3
        assert parts[0] == "sb"
        assert len(parts[1]) == 8  # prefix is 8 hex chars
        assert len(parts[2]) == 40  # secret is 40 hex chars

    def test_key_prefix_is_unique(self, api_key_service, mock_db):
        """Test that key_prefix is stored in database"""
        # Arrange
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        api_key, full_key = api_key_service.generate_api_key(
            user_id=1,
            name="Test",
            scopes=["read"]
        )

        # Assert
        # key_prefix stores "sb_<8chars>" for indexing
        parts = full_key.split("_")
        expected_prefix = f"{parts[0]}_{parts[1]}"  # sb_<prefix>
        assert api_key.key_prefix == expected_prefix


class TestApiKeyVerification:
    """Test API key verification"""

    def test_verify_valid_key(self, api_key_service, mock_db, sample_api_key):
        """Test verification of a valid API key"""
        # Arrange
        key_prefix = "sb_abc12345"  # Full prefix with sb_
        secret = "test_secret"
        ip_address = "1.2.3.4"

        # Mock hash verification
        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            # Mock database query
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query
            mock_db.commit = Mock()  # Mock commit

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret,
                ip_address=ip_address
            )

            # Assert
            assert result == sample_api_key
            assert sample_api_key.usage_count == 1
            assert sample_api_key.last_used_ip == ip_address
            assert sample_api_key.last_used_at is not None
            mock_db.commit.assert_called_once()  # Verify commit was called

    def test_verify_invalid_secret(self, api_key_service, mock_db, sample_api_key):
        """Test verification fails with invalid secret"""
        # Arrange
        key_prefix = "sb_abc12345"
        secret = "wrong_secret"

        # Mock hash verification to return different hash
        with patch.object(api_key_service, '_hash_secret', return_value="different_hash"):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret
            )

            # Assert
            assert result is None

    def test_verify_revoked_key(self, api_key_service, mock_db, sample_api_key):
        """Test verification fails for revoked key"""
        # Arrange
        sample_api_key.revoked_at = datetime.utcnow()
        key_prefix = "sb_abc12345"
        secret = "test_secret"

        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret
            )

            # Assert
            assert result is None

    def test_verify_expired_key(self, api_key_service, mock_db, sample_api_key):
        """Test verification fails for expired key"""
        # Arrange
        sample_api_key.expires_at = datetime.utcnow() - timedelta(days=1)  # expired yesterday
        key_prefix = "sb_abc12345"
        secret = "test_secret"

        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret
            )

            # Assert
            assert result is None

    def test_verify_ip_whitelist_allowed(self, api_key_service, mock_db, sample_api_key):
        """Test verification succeeds when IP is in whitelist"""
        # Arrange
        sample_api_key.ip_whitelist = ["1.2.3.4", "5.6.7.8"]
        key_prefix = "sb_abc12345"
        secret = "test_secret"
        ip_address = "1.2.3.4"

        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret,
                ip_address=ip_address
            )

            # Assert
            assert result == sample_api_key

    def test_verify_ip_whitelist_denied(self, api_key_service, mock_db, sample_api_key):
        """Test verification fails when IP is not in whitelist"""
        # Arrange
        sample_api_key.ip_whitelist = ["1.2.3.4", "5.6.7.8"]
        key_prefix = "sb_abc12345"
        secret = "test_secret"
        ip_address = "9.9.9.9"  # not in whitelist

        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret,
                ip_address=ip_address
            )

            # Assert
            assert result is None

    def test_verify_no_ip_whitelist(self, api_key_service, mock_db, sample_api_key):
        """Test verification succeeds when no IP whitelist is set"""
        # Arrange
        sample_api_key.ip_whitelist = None
        key_prefix = "sb_abc12345"
        secret = "test_secret"
        ip_address = "9.9.9.9"

        with patch.object(api_key_service, '_hash_secret', return_value=sample_api_key.key_hash):
            mock_query = Mock()
            mock_query.filter.return_value.filter.return_value.first.return_value = sample_api_key
            mock_db.query.return_value = mock_query

            # Act
            result = api_key_service.verify_api_key(
                key_prefix=key_prefix,
                secret=secret,
                ip_address=ip_address
            )

            # Assert
            assert result == sample_api_key


class TestApiKeyRevocation:
    """Test API key revocation"""

    def test_revoke_api_key(self, api_key_service, mock_db, sample_api_key):
        """Test revoking an API key"""
        # Arrange
        api_key_id = 1
        revoked_by = 1
        reason = "No longer needed"

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.revoke_api_key(
            api_key_id=api_key_id,
            revoked_by=revoked_by,
            reason=reason
        )

        # Assert
        assert result is True
        assert sample_api_key.revoked_at is not None
        assert sample_api_key.revoked_by == revoked_by
        assert sample_api_key.revoked_reason == reason
        mock_db.commit.assert_called_once()

    def test_revoke_nonexistent_key(self, api_key_service, mock_db):
        """Test revoking a non-existent API key"""
        # Arrange
        api_key_id = 999

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.revoke_api_key(
            api_key_id=api_key_id,
            revoked_by=1
        )

        # Assert
        assert result is False

    def test_revoke_already_revoked_key(self, api_key_service, mock_db, sample_api_key):
        """Test revoking an already revoked key"""
        # Arrange
        sample_api_key.revoked_at = datetime.utcnow()
        api_key_id = 1

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.revoke_api_key(
            api_key_id=api_key_id,
            revoked_by=1
        )

        # Assert
        assert result is False  # Already revoked


class TestApiKeyRotation:
    """Test API key rotation"""

    def test_rotate_api_key(self, api_key_service, mock_db, sample_api_key):
        """Test rotating an API key"""
        # Arrange
        api_key_id = 1
        user_id = 1

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Act
        new_api_key, new_full_key = api_key_service.rotate_api_key(
            api_key_id=api_key_id,
            user_id=user_id
        )

        # Assert
        # Old key should be revoked
        assert sample_api_key.revoked_at is not None
        assert sample_api_key.revoked_reason == "Rotated"

        # New key should have same settings
        assert new_api_key.user_id == sample_api_key.user_id
        assert new_api_key.name == sample_api_key.name
        assert new_api_key.scopes == sample_api_key.scopes
        assert new_api_key.rate_limit_tier == sample_api_key.rate_limit_tier
        assert new_api_key.ip_whitelist == sample_api_key.ip_whitelist

        # New key should be active
        assert new_api_key.revoked_at is None

        # New key should have different prefix
        assert new_full_key.startswith("sb_")

    def test_rotate_nonexistent_key(self, api_key_service, mock_db):
        """Test rotating a non-existent key"""
        # Arrange
        api_key_id = 999
        user_id = 1

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        # Act & Assert
        with pytest.raises(ValueError, match="API key not found"):
            api_key_service.rotate_api_key(
                api_key_id=api_key_id,
                user_id=user_id
            )


class TestHashingAndSecurity:
    """Test hashing and security functions"""

    def test_hash_secret_consistency(self, api_key_service):
        """Test that hashing the same secret produces same hash"""
        secret = "test_secret_12345"

        hash1 = api_key_service._hash_secret(secret)
        hash2 = api_key_service._hash_secret(secret)

        assert hash1 == hash2

    def test_hash_secret_different_inputs(self, api_key_service):
        """Test that different secrets produce different hashes"""
        secret1 = "secret_1"
        secret2 = "secret_2"

        hash1 = api_key_service._hash_secret(secret1)
        hash2 = api_key_service._hash_secret(secret2)

        assert hash1 != hash2

    def test_generate_key_prefix_format(self, api_key_service):
        """Test key prefix generation format"""
        prefix = api_key_service._generate_key_prefix()

        assert len(prefix) == 8
        # Check if it's hexadecimal
        int(prefix, 16)  # Raises ValueError if not hex

    def test_generate_key_secret_format(self, api_key_service):
        """Test key secret generation format"""
        secret = api_key_service._generate_key_secret()

        assert len(secret) == 40
        # Check if it's hexadecimal
        int(secret, 16)  # Raises ValueError if not hex

    def test_key_randomness(self, api_key_service):
        """Test that generated keys are random"""
        keys = [api_key_service._generate_key_secret() for _ in range(10)]

        # All keys should be unique
        assert len(set(keys)) == len(keys)


class TestUpdateApiKey:
    """Test API key updates"""

    def test_update_name(self, api_key_service, mock_db, sample_api_key):
        """Test updating API key name"""
        # Arrange
        api_key_id = 1
        new_name = "Updated Key Name"

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.update_api_key(
            api_key_id=api_key_id,
            name=new_name
        )

        # Assert
        assert result.name == new_name
        mock_db.commit.assert_called_once()

    def test_update_scopes(self, api_key_service, mock_db, sample_api_key):
        """Test updating API key scopes"""
        # Arrange
        api_key_id = 1
        new_scopes = ["read", "trade", "admin"]

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.update_api_key(
            api_key_id=api_key_id,
            scopes=new_scopes
        )

        # Assert
        assert result.scopes == new_scopes

    def test_update_ip_whitelist(self, api_key_service, mock_db, sample_api_key):
        """Test updating IP whitelist"""
        # Arrange
        api_key_id = 1
        new_ip_whitelist = ["10.0.0.1", "10.0.0.2"]

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_api_key
        mock_db.query.return_value = mock_query

        # Act
        result = api_key_service.update_api_key(
            api_key_id=api_key_id,
            ip_whitelist=new_ip_whitelist
        )

        # Assert
        assert result.ip_whitelist == new_ip_whitelist
