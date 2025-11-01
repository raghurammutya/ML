"""
Unit tests for authentication module
"""
import pytest
from fastapi import HTTPException

from app.auth import verify_api_key
from app.config import Settings


@pytest.mark.unit
async def test_verify_api_key_disabled():
    """Test that authentication can be disabled"""
    # When API key is disabled, should return success
    result = await verify_api_key(x_api_key=None)
    assert result == "auth_disabled"


@pytest.mark.unit
async def test_verify_api_key_missing(monkeypatch):
    """Test that missing API key raises 401"""
    # Enable API key authentication
    def mock_get_settings():
        return Settings(
            api_key_enabled=True,
            api_key="test-key-123",
            environment="test"
        )

    monkeypatch.setattr("app.auth.get_settings", mock_get_settings)

    # Missing key should raise exception
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(x_api_key=None)

    assert exc_info.value.status_code == 401
    assert "Missing API key" in exc_info.value.detail


@pytest.mark.unit
async def test_verify_api_key_invalid(monkeypatch):
    """Test that invalid API key raises 401"""
    def mock_get_settings():
        return Settings(
            api_key_enabled=True,
            api_key="correct-key",
            environment="test"
        )

    monkeypatch.setattr("app.auth.get_settings", mock_get_settings)

    # Wrong key should raise exception
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(x_api_key="wrong-key")

    assert exc_info.value.status_code == 401
    assert "Invalid API key" in exc_info.value.detail


@pytest.mark.unit
async def test_verify_api_key_valid(monkeypatch):
    """Test that valid API key succeeds"""
    correct_key = "correct-key-456"

    def mock_get_settings():
        return Settings(
            api_key_enabled=True,
            api_key=correct_key,
            environment="test"
        )

    monkeypatch.setattr("app.auth.get_settings", mock_get_settings)

    # Correct key should succeed
    result = await verify_api_key(x_api_key=correct_key)
    assert result == correct_key
