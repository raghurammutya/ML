"""
Tick validation service.

Validates incoming tick data using Pydantic schemas to catch malformed data early.
Phase 4 - Performance & Observability.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator

from loguru import logger

from ..metrics import record_validation_error


class TickValidationError(Exception):
    """Raised when tick validation fails"""
    pass


class UnderlyingTickSchema(BaseModel):
    """Schema for underlying/index ticks"""
    instrument_token: int = Field(..., description="Instrument token")
    last_price: float = Field(..., description="Last traded price")
    volume: Optional[int] = Field(None, description="Volume traded")
    timestamp: Optional[int] = Field(None, description="Tick timestamp")

    @field_validator('instrument_token')
    @classmethod
    def validate_instrument_token(cls, v):
        if v <= 0:
            raise ValueError("Instrument token must be positive")
        return v

    @field_validator('last_price')
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError("Price must be positive")
        if v > 1000000:  # Sanity check - 10 lakh rupees
            raise ValueError("Price unreasonably high (> 10,00,000)")
        return v

    @field_validator('volume')
    @classmethod
    def validate_volume(cls, v):
        if v is not None and v < 0:
            raise ValueError("Volume cannot be negative")
        return v

    class Config:
        extra = "allow"  # Allow extra fields from WebSocket


class OptionTickSchema(BaseModel):
    """Schema for option ticks"""
    instrument_token: int = Field(..., description="Instrument token")
    last_price: float = Field(..., description="Last traded price")
    volume: Optional[int] = Field(None, description="Volume traded")
    oi: Optional[int] = Field(None, description="Open interest")
    timestamp: Optional[int] = Field(None, description="Tick timestamp")

    @field_validator('instrument_token')
    @classmethod
    def validate_instrument_token(cls, v):
        if v <= 0:
            raise ValueError("Instrument token must be positive")
        return v

    @field_validator('last_price')
    @classmethod
    def validate_price(cls, v):
        if v < 0:
            raise ValueError("Option price cannot be negative")
        if v > 100000:  # Sanity check - 1 lakh rupees for option premium
            raise ValueError("Option price unreasonably high (> 1,00,000)")
        return v

    @field_validator('volume')
    @classmethod
    def validate_volume(cls, v):
        if v is not None and v < 0:
            raise ValueError("Volume cannot be negative")
        return v

    @field_validator('oi')
    @classmethod
    def validate_oi(cls, v):
        if v is not None and v < 0:
            raise ValueError("Open interest cannot be negative")
        return v

    class Config:
        extra = "allow"  # Allow extra fields from WebSocket


class TickValidator:
    """
    Validates incoming tick data.

    Features:
    - Schema validation using Pydantic
    - Business rule validation
    - Configurable strict mode
    - Error tracking with metrics
    """

    def __init__(self, strict_mode: bool = False, enabled: bool = True):
        """
        Initialize validator.

        Args:
            strict_mode: If True, raise exceptions on validation errors
            enabled: If False, skip all validation (for testing)
        """
        self._strict_mode = strict_mode
        self._enabled = enabled
        self._validation_errors: List[str] = []

    def validate_underlying_tick(self, tick: Dict[str, Any]) -> bool:
        """
        Validate underlying tick data.

        Args:
            tick: Raw tick data

        Returns:
            True if valid, False otherwise
        """
        if not self._enabled:
            return True

        try:
            # Prepare data for validation
            data = {
                "instrument_token": tick.get("instrument_token"),
                "last_price": tick.get("last_price"),
                "volume": tick.get("volume_traded_today") or tick.get("volume"),
                "timestamp": tick.get("timestamp"),
            }

            # Validate with schema
            UnderlyingTickSchema(**data)
            return True

        except ValueError as e:
            error_msg = f"Underlying tick validation failed: {e}"
            self._validation_errors.append(error_msg)
            record_validation_error("schema")
            logger.debug(error_msg)

            if self._strict_mode:
                raise TickValidationError(error_msg) from e

            return False

        except Exception as e:
            error_msg = f"Unexpected validation error: {e}"
            self._validation_errors.append(error_msg)
            record_validation_error("unexpected")
            logger.error(error_msg)

            if self._strict_mode:
                raise TickValidationError(error_msg) from e

            return False

    def validate_option_tick(self, tick: Dict[str, Any]) -> bool:
        """
        Validate option tick data.

        Args:
            tick: Raw tick data

        Returns:
            True if valid, False otherwise
        """
        if not self._enabled:
            return True

        try:
            # Prepare data for validation
            data = {
                "instrument_token": tick.get("instrument_token"),
                "last_price": tick.get("last_price"),
                "volume": tick.get("volume_traded_today") or tick.get("volume"),
                "oi": tick.get("oi") or tick.get("open_interest"),
                "timestamp": tick.get("timestamp"),
            }

            # Validate with schema
            OptionTickSchema(**data)

            # Additional business rules
            if not self._validate_business_rules(tick):
                return False

            return True

        except ValueError as e:
            error_msg = f"Option tick validation failed: {e}"
            self._validation_errors.append(error_msg)
            record_validation_error("schema")
            logger.debug(error_msg)

            if self._strict_mode:
                raise TickValidationError(error_msg) from e

            return False

        except Exception as e:
            error_msg = f"Unexpected validation error: {e}"
            self._validation_errors.append(error_msg)
            record_validation_error("unexpected")
            logger.error(error_msg)

            if self._strict_mode:
                raise TickValidationError(error_msg) from e

            return False

    def _validate_business_rules(self, tick: Dict[str, Any]) -> bool:
        """
        Validate business rules for option ticks.

        Args:
            tick: Raw tick data

        Returns:
            True if valid, False otherwise
        """
        # Example business rule: OI should be reasonable
        oi = tick.get("oi") or tick.get("open_interest") or 0
        if oi > 100000000:  # 10 crore contracts
            error_msg = f"Open interest unreasonably high: {oi}"
            self._validation_errors.append(error_msg)
            record_validation_error("business_rule")
            logger.warning(error_msg)

            if self._strict_mode:
                raise TickValidationError(error_msg)

            return False

        return True

    def validate_batch(
        self,
        ticks: List[Dict[str, Any]],
        instrument_type: str
    ) -> List[Dict[str, Any]]:
        """
        Validate a batch of ticks and return only valid ones.

        Args:
            ticks: List of raw tick data
            instrument_type: "underlying" or "option"

        Returns:
            List of valid ticks
        """
        if not self._enabled:
            return ticks

        valid_ticks = []

        for tick in ticks:
            is_valid = False

            if instrument_type == "underlying":
                is_valid = self.validate_underlying_tick(tick)
            elif instrument_type == "option":
                is_valid = self.validate_option_tick(tick)
            else:
                logger.warning(f"Unknown instrument type: {instrument_type}")
                continue

            if is_valid:
                valid_ticks.append(tick)

        if len(valid_ticks) < len(ticks):
            filtered = len(ticks) - len(valid_ticks)
            logger.info(f"Filtered {filtered} invalid ticks from batch of {len(ticks)}")

        return valid_ticks

    def get_validation_errors(self) -> List[str]:
        """Get list of validation errors"""
        return self._validation_errors.copy()

    def clear_errors(self) -> None:
        """Clear validation error history"""
        self._validation_errors.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get validator statistics"""
        return {
            "enabled": self._enabled,
            "strict_mode": self._strict_mode,
            "error_count": len(self._validation_errors),
        }
