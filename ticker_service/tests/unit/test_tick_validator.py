"""
Unit tests for TickValidator.

Tests schema validation, business rule validation, and batch filtering.
"""
import pytest

from app.services.tick_validator import (
    TickValidator,
    TickValidationError,
    UnderlyingTickSchema,
    OptionTickSchema,
)


class TestUnderlyingTickSchema:
    """Test UnderlyingTickSchema validation"""

    def test_valid_underlying_tick(self):
        """Test valid underlying tick passes validation"""
        data = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "volume": 1000000,
            "timestamp": 1234567890,
        }
        schema = UnderlyingTickSchema(**data)
        assert schema.instrument_token == 256265
        assert schema.last_price == 24000.50
        assert schema.volume == 1000000
        assert schema.timestamp == 1234567890

    def test_minimal_valid_tick(self):
        """Test minimal valid tick with only required fields"""
        data = {
            "instrument_token": 256265,
            "last_price": 24000.50,
        }
        schema = UnderlyingTickSchema(**data)
        assert schema.instrument_token == 256265
        assert schema.last_price == 24000.50
        assert schema.volume is None
        assert schema.timestamp is None

    def test_negative_instrument_token(self):
        """Test negative instrument token is rejected"""
        data = {
            "instrument_token": -1,
            "last_price": 24000.50,
        }
        with pytest.raises(ValueError, match="Instrument token must be positive"):
            UnderlyingTickSchema(**data)

    def test_zero_instrument_token(self):
        """Test zero instrument token is rejected"""
        data = {
            "instrument_token": 0,
            "last_price": 24000.50,
        }
        with pytest.raises(ValueError, match="Instrument token must be positive"):
            UnderlyingTickSchema(**data)

    def test_zero_price(self):
        """Test zero price is rejected"""
        data = {
            "instrument_token": 256265,
            "last_price": 0.0,
        }
        with pytest.raises(ValueError, match="Price must be positive"):
            UnderlyingTickSchema(**data)

    def test_negative_price(self):
        """Test negative price is rejected"""
        data = {
            "instrument_token": 256265,
            "last_price": -100.0,
        }
        with pytest.raises(ValueError, match="Price must be positive"):
            UnderlyingTickSchema(**data)

    def test_unreasonably_high_price(self):
        """Test unreasonably high price is rejected"""
        data = {
            "instrument_token": 256265,
            "last_price": 2000000.0,  # 20 lakh rupees
        }
        with pytest.raises(ValueError, match="Price unreasonably high"):
            UnderlyingTickSchema(**data)

    def test_negative_volume(self):
        """Test negative volume is rejected"""
        data = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "volume": -1000,
        }
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            UnderlyingTickSchema(**data)

    def test_extra_fields_allowed(self):
        """Test extra fields are allowed (WebSocket sends many fields)"""
        data = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "extra_field": "should be allowed",
            "another_field": 123,
        }
        schema = UnderlyingTickSchema(**data)
        assert schema.instrument_token == 256265


class TestOptionTickSchema:
    """Test OptionTickSchema validation"""

    def test_valid_option_tick(self):
        """Test valid option tick passes validation"""
        data = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "volume": 50000,
            "oi": 1000000,
            "timestamp": 1234567890,
        }
        schema = OptionTickSchema(**data)
        assert schema.instrument_token == 12345678
        assert schema.last_price == 150.50
        assert schema.volume == 50000
        assert schema.oi == 1000000

    def test_zero_option_price_allowed(self):
        """Test zero price is allowed for options (far OTM)"""
        data = {
            "instrument_token": 12345678,
            "last_price": 0.0,
        }
        schema = OptionTickSchema(**data)
        assert schema.last_price == 0.0

    def test_negative_option_price(self):
        """Test negative price is rejected for options"""
        data = {
            "instrument_token": 12345678,
            "last_price": -10.0,
        }
        with pytest.raises(ValueError, match="Option price cannot be negative"):
            OptionTickSchema(**data)

    def test_unreasonably_high_option_price(self):
        """Test unreasonably high option price is rejected"""
        data = {
            "instrument_token": 12345678,
            "last_price": 150000.0,  # 1.5 lakh rupees
        }
        with pytest.raises(ValueError, match="Option price unreasonably high"):
            OptionTickSchema(**data)

    def test_negative_oi(self):
        """Test negative open interest is rejected"""
        data = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "oi": -1000,
        }
        with pytest.raises(ValueError, match="Open interest cannot be negative"):
            OptionTickSchema(**data)


class TestTickValidator:
    """Test TickValidator functionality"""

    def test_validator_initialization(self):
        """Test validator can be initialized"""
        validator = TickValidator()
        assert validator._enabled is True
        assert validator._strict_mode is False

    def test_validator_disabled(self):
        """Test disabled validator always returns True"""
        validator = TickValidator(enabled=False)

        # Invalid tick should pass when validator is disabled
        invalid_tick = {
            "instrument_token": -1,
            "last_price": -100.0,
        }
        assert validator.validate_underlying_tick(invalid_tick) is True
        assert validator.validate_option_tick(invalid_tick) is True

    def test_validate_valid_underlying_tick(self):
        """Test valid underlying tick passes validation"""
        validator = TickValidator()
        tick = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "volume_traded_today": 1000000,
            "timestamp": 1234567890,
        }
        assert validator.validate_underlying_tick(tick) is True

    def test_validate_invalid_underlying_tick(self):
        """Test invalid underlying tick fails validation (non-strict mode)"""
        validator = TickValidator()
        tick = {
            "instrument_token": 256265,
            "last_price": -100.0,  # Invalid: negative price
        }
        assert validator.validate_underlying_tick(tick) is False

        # Check error was recorded
        errors = validator.get_validation_errors()
        assert len(errors) > 0
        assert "validation failed" in errors[0].lower()

    def test_validate_invalid_underlying_tick_strict(self):
        """Test invalid underlying tick raises exception in strict mode"""
        validator = TickValidator(strict_mode=True)
        tick = {
            "instrument_token": 256265,
            "last_price": -100.0,  # Invalid: negative price
        }
        with pytest.raises(TickValidationError):
            validator.validate_underlying_tick(tick)

    def test_validate_valid_option_tick(self):
        """Test valid option tick passes validation"""
        validator = TickValidator()
        tick = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "volume_traded_today": 50000,
            "oi": 1000000,
            "timestamp": 1234567890,
        }
        assert validator.validate_option_tick(tick) is True

    def test_validate_invalid_option_tick(self):
        """Test invalid option tick fails validation (non-strict mode)"""
        validator = TickValidator()
        tick = {
            "instrument_token": 12345678,
            "last_price": -10.0,  # Invalid: negative price
        }
        assert validator.validate_option_tick(tick) is False

    def test_validate_option_tick_business_rule_violation(self):
        """Test option tick with business rule violation"""
        validator = TickValidator()
        tick = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "oi": 200000000,  # Invalid: 20 crore contracts (unreasonably high)
        }
        assert validator.validate_option_tick(tick) is False

        errors = validator.get_validation_errors()
        assert len(errors) > 0
        assert "unreasonably high" in errors[0].lower()

    def test_validate_option_tick_business_rule_strict(self):
        """Test business rule violation raises exception in strict mode"""
        validator = TickValidator(strict_mode=True)
        tick = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "oi": 200000000,  # Invalid: unreasonably high
        }
        with pytest.raises(TickValidationError):
            validator.validate_option_tick(tick)

    def test_validate_batch_underlying(self):
        """Test batch validation for underlying ticks"""
        validator = TickValidator()
        ticks = [
            {"instrument_token": 256265, "last_price": 24000.50},  # Valid
            {"instrument_token": 256266, "last_price": -100.0},     # Invalid
            {"instrument_token": 256267, "last_price": 24100.00},  # Valid
        ]

        valid_ticks = validator.validate_batch(ticks, "underlying")
        assert len(valid_ticks) == 2
        assert valid_ticks[0]["instrument_token"] == 256265
        assert valid_ticks[1]["instrument_token"] == 256267

    def test_validate_batch_options(self):
        """Test batch validation for option ticks"""
        validator = TickValidator()
        ticks = [
            {"instrument_token": 12345678, "last_price": 150.50, "oi": 1000000},  # Valid
            {"instrument_token": 12345679, "last_price": -10.0, "oi": 500000},    # Invalid price
            {"instrument_token": 12345680, "last_price": 200.00, "oi": 200000000},  # Invalid OI
            {"instrument_token": 12345681, "last_price": 175.25, "oi": 800000},  # Valid
        ]

        valid_ticks = validator.validate_batch(ticks, "option")
        assert len(valid_ticks) == 2
        assert valid_ticks[0]["instrument_token"] == 12345678
        assert valid_ticks[1]["instrument_token"] == 12345681

    def test_validate_batch_disabled(self):
        """Test batch validation when disabled returns all ticks"""
        validator = TickValidator(enabled=False)
        ticks = [
            {"instrument_token": 256265, "last_price": -100.0},  # Invalid but should pass
            {"instrument_token": 256266, "last_price": -200.0},  # Invalid but should pass
        ]

        valid_ticks = validator.validate_batch(ticks, "underlying")
        assert len(valid_ticks) == 2

    def test_validate_batch_unknown_type(self):
        """Test batch validation with unknown instrument type"""
        validator = TickValidator()
        ticks = [
            {"instrument_token": 256265, "last_price": 24000.50},
        ]

        valid_ticks = validator.validate_batch(ticks, "unknown_type")
        assert len(valid_ticks) == 0

    def test_clear_errors(self):
        """Test clearing validation error history"""
        validator = TickValidator()

        # Generate some errors
        invalid_tick = {"instrument_token": 256265, "last_price": -100.0}
        validator.validate_underlying_tick(invalid_tick)

        assert len(validator.get_validation_errors()) > 0

        # Clear errors
        validator.clear_errors()
        assert len(validator.get_validation_errors()) == 0

    def test_get_stats(self):
        """Test getting validator statistics"""
        validator = TickValidator(strict_mode=False, enabled=True)

        # Generate some errors (non-strict mode)
        invalid_tick = {"instrument_token": 256265, "last_price": -100.0}
        validator.validate_underlying_tick(invalid_tick)

        stats = validator.get_stats()
        assert stats["enabled"] is True
        assert stats["strict_mode"] is False
        assert stats["error_count"] > 0

    def test_field_mapping_volume_traded_today(self):
        """Test field mapping for volume_traded_today"""
        validator = TickValidator()
        tick = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "volume_traded_today": 1000000,  # WebSocket field name
        }
        assert validator.validate_underlying_tick(tick) is True

    def test_field_mapping_volume(self):
        """Test field mapping for volume"""
        validator = TickValidator()
        tick = {
            "instrument_token": 256265,
            "last_price": 24000.50,
            "volume": 1000000,  # Alternative field name
        }
        assert validator.validate_underlying_tick(tick) is True

    def test_field_mapping_open_interest(self):
        """Test field mapping for open_interest"""
        validator = TickValidator()
        tick = {
            "instrument_token": 12345678,
            "last_price": 150.50,
            "open_interest": 1000000,  # Alternative field name
        }
        assert validator.validate_option_tick(tick) is True

    def test_missing_required_fields(self):
        """Test missing required fields"""
        validator = TickValidator()

        # Missing instrument_token
        tick = {"last_price": 24000.50}
        assert validator.validate_underlying_tick(tick) is False

        # Missing last_price
        tick = {"instrument_token": 256265}
        assert validator.validate_underlying_tick(tick) is False
