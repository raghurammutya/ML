"""
Unit tests for configuration module
"""
import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.unit
def test_settings_defaults():
    """Test that settings have reasonable defaults"""
    settings = Settings(environment="test")

    assert settings.app_name == "ticker-service"
    assert settings.environment == "test"
    assert settings.redis_url.startswith("redis://")
    assert settings.max_instruments_per_ws_connection == 3000  # Updated from 1000 to 3000


@pytest.mark.unit
def test_settings_api_key_validation():
    """Test that API key is required when authentication is enabled"""
    # Should raise error if API key enabled but not provided
    with pytest.raises(ValidationError, match="api_key must be set"):
        Settings(
            environment="test",
            api_key_enabled=True,
            api_key=""
        )


@pytest.mark.unit
def test_settings_production_requires_auth():
    """Test that production environment enforces authentication"""
    # Production must have auth enabled
    with pytest.raises(ValidationError, match="API key authentication MUST be enabled"):
        Settings(
            environment="production",
            api_key_enabled=False
        )


@pytest.mark.unit
def test_settings_positive_integers():
    """Test validation of positive integer fields"""
    # Should reject negative values
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            option_expiry_window=-1
        )

    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            otm_levels=0
        )


@pytest.mark.unit
def test_settings_port_validation():
    """Test that database port is validated"""
    # Invalid port should raise error
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            instrument_db_port=99999
        )

    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            instrument_db_port=0
        )


@pytest.mark.unit
def test_settings_ticker_mode_validation():
    """Test that ticker mode is validated"""
    # Invalid mode should raise error
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            ticker_mode="invalid"
        )

    # Valid modes should work
    for mode in ["full", "quote", "ltp", "FULL", "QUOTE", "LTP"]:
        settings = Settings(environment="test", ticker_mode=mode)
        assert settings.ticker_mode.lower() in ["full", "quote", "ltp"]
