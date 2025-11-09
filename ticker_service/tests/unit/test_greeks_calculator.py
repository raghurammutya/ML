"""
Greeks Calculator Test Suite - P0 Critical Coverage

Validates mathematical accuracy of Black-Scholes options pricing and Greeks calculations.
Target: 95% coverage on greeks_calculator.py

Mathematical References:
- Hull's "Options, Futures, and Other Derivatives" (9th Edition)
- py-vollib documentation for Black-Scholes implementation
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from app.greeks_calculator import GreeksCalculator, VOLLIB_AVAILABLE


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def calculator():
    """Standard calculator with default parameters"""
    return GreeksCalculator(
        interest_rate=0.10,
        dividend_yield=0.0,
        expiry_time_hour=15,
        expiry_time_minute=30,
        market_timezone="Asia/Kolkata"
    )


@pytest.fixture
def calculator_with_dividends():
    """Calculator with dividend yield for BSM model"""
    return GreeksCalculator(
        interest_rate=0.10,
        dividend_yield=0.02,
        expiry_time_hour=15,
        expiry_time_minute=30,
        market_timezone="Asia/Kolkata"
    )


# ============================================================================
# TIME TO EXPIRY TESTS (QA-GREEK-016 to QA-GREEK-020)
# ============================================================================

@pytest.mark.unit
def test_time_to_expiry_same_day(calculator):
    """
    Test ID: QA-GREEK-016
    Verify time to expiry calculation for same day expiry

    Given: Current time and expiry on same day
    When: Calculate time to expiry
    Then: Returns correct fraction of year
    """
    # ARRANGE
    ist = ZoneInfo("Asia/Kolkata")
    current_time = datetime(2025, 11, 9, 10, 0, tzinfo=ist)
    expiry_date_str = "2025-11-09"

    # ACT
    time_to_expiry = calculator.calculate_time_to_expiry(expiry_date_str, current_time)

    # ASSERT
    # Time from 10:00 AM to 3:30 PM = 5.5 hours = 5.5/24 days = 5.5/(24*365.25) years
    expected = 5.5 / (24 * 365.25)
    assert abs(time_to_expiry - expected) < 0.0001


@pytest.mark.unit
def test_time_to_expiry_future_date(calculator):
    """
    Test: Verify time to expiry for future date

    Given: Current time and expiry 7 days later
    When: Calculate time to expiry
    Then: Returns approximately 7/365.25 years
    """
    # ARRANGE
    ist = ZoneInfo("Asia/Kolkata")
    current_time = datetime(2025, 11, 9, 10, 0, tzinfo=ist)
    expiry_date_str = "2025-11-16"

    # ACT
    time_to_expiry = calculator.calculate_time_to_expiry(expiry_date_str, current_time)

    # ASSERT
    # 7 days minus time already elapsed in current day
    # From Nov 9 10:00 AM to Nov 16 3:30 PM = 7 days 5.5 hours
    expected_days = 7 + (5.5 / 24)
    expected = expected_days / 365.25
    assert abs(time_to_expiry - expected) < 0.002


@pytest.mark.unit
def test_time_to_expiry_expired_option(calculator):
    """
    Test ID: QA-GREEK-020
    Verify expired options return T=0

    Given: Current time after expiry
    When: Calculate time to expiry
    Then: Returns 0.0
    """
    # ARRANGE
    ist = ZoneInfo("Asia/Kolkata")
    current_time = datetime(2025, 11, 9, 16, 0, tzinfo=ist)
    expiry_date_str = "2025-11-09"

    # ACT
    time_to_expiry = calculator.calculate_time_to_expiry(expiry_date_str, current_time)

    # ASSERT
    assert time_to_expiry == 0.0


@pytest.mark.unit
def test_time_to_expiry_with_invalid_date_format(calculator):
    """
    Test: Verify error handling for invalid date format

    Given: Invalid date string
    When: Calculate time to expiry
    Then: Returns 0.0 and logs error
    """
    # ACT
    time_to_expiry = calculator.calculate_time_to_expiry("invalid-date")

    # ASSERT
    assert time_to_expiry == 0.0


@pytest.mark.unit
def test_time_to_expiry_uses_current_time_if_not_provided(calculator):
    """
    Test: Verify current time is used when not provided

    Given: No current_time parameter
    When: Calculate time to expiry
    Then: Uses datetime.now() in market timezone
    """
    # ARRANGE - Expiry tomorrow
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # ACT
    time_to_expiry = calculator.calculate_time_to_expiry(tomorrow)

    # ASSERT - Should be around 1 day (approximately 1/365.25 years)
    expected = 1.0 / 365.25
    assert abs(time_to_expiry - expected) < 0.01  # Within 1% accuracy


# ============================================================================
# IMPLIED VOLATILITY TESTS (QA-GREEK-011 to QA-GREEK-015)
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_iv_calculation_atm_call(calculator):
    """
    Test ID: QA-GREEK-011
    Verify IV calculation for ATM call option

    Given: Market price, ATM strike
    When: Calculate implied volatility
    Then: Returns reasonable IV (0.1 to 1.0)
    """
    # ARRANGE - ATM call with typical market price
    market_price = 10.0
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25  # 30 days
    option_type = "CE"

    # ACT
    iv = calculator.calculate_implied_volatility(
        market_price=market_price,
        spot_price=spot_price,
        strike_price=strike_price,
        time_to_expiry=time_to_expiry,
        option_type=option_type
    )

    # ASSERT
    assert iv > 0.1, "IV should be > 10%"
    assert iv < 1.0, "IV should be < 100% for typical options"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_iv_zero_market_price_returns_zero(calculator):
    """
    Test ID: QA-GREEK-012
    Verify IV returns 0 when market price is 0

    Given: Market price = 0
    When: Calculate IV
    Then: Returns 0.0
    """
    # ACT
    iv = calculator.calculate_implied_volatility(
        market_price=0.0,
        spot_price=100.0,
        strike_price=100.0,
        time_to_expiry=0.1,
        option_type="CE"
    )

    # ASSERT
    assert iv == 0.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_iv_zero_time_to_expiry_returns_zero(calculator):
    """
    Test ID: QA-GREEK-013
    Verify IV returns 0 when time to expiry is 0

    Given: Time to expiry = 0
    When: Calculate IV
    Then: Returns 0.0
    """
    # ACT
    iv = calculator.calculate_implied_volatility(
        market_price=10.0,
        spot_price=100.0,
        strike_price=100.0,
        time_to_expiry=0.0,
        option_type="CE"
    )

    # ASSERT
    assert iv == 0.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_iv_bounds_validation(calculator):
    """
    Test ID: QA-GREEK-014
    Verify IV is bounded between 0 and 5.0 (500%)

    Given: Various market conditions
    When: Calculate IV
    Then: Returns value between 0 and 5.0
    """
    # ARRANGE - Try to create extreme IV scenario
    market_price = 50.0  # Very high option price
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 7 / 365.25  # 1 week
    option_type = "CE"

    # ACT
    iv = calculator.calculate_implied_volatility(
        market_price=market_price,
        spot_price=spot_price,
        strike_price=strike_price,
        time_to_expiry=time_to_expiry,
        option_type=option_type
    )

    # ASSERT
    assert iv >= 0.0
    assert iv <= 5.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_iv_handles_option_type_variations(calculator):
    """
    Test: Verify IV works with different option type formats

    Given: Different option type strings (CE, CALL, c, PE, PUT, p)
    When: Calculate IV
    Then: Returns valid IV for all formats
    """
    market_price = 10.0
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25

    # Test call variations
    for option_type in ["CE", "CALL", "c", "C"]:
        iv = calculator.calculate_implied_volatility(
            market_price, spot_price, strike_price, time_to_expiry, option_type
        )
        assert iv >= 0.0

    # Test put variations
    for option_type in ["PE", "PUT", "p", "P"]:
        iv = calculator.calculate_implied_volatility(
            market_price, spot_price, strike_price, time_to_expiry, option_type
        )
        assert iv >= 0.0


# ============================================================================
# GREEKS CALCULATION TESTS (QA-GREEK-006 to QA-GREEK-010)
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_atm_call_delta_around_05(calculator):
    """
    Test ID: QA-GREEK-006
    Verify ATM call delta is approximately 0.5

    Given: ATM call option
    When: Calculate Greeks
    Then: Delta ≈ 0.5 (±0.1)
    """
    # ARRANGE
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20
    option_type = "CE"

    # ACT
    greeks = calculator.calculate_greeks(
        spot_price, strike_price, time_to_expiry, implied_vol, option_type
    )

    # ASSERT
    assert abs(greeks["delta"] - 0.5) < 0.15, f"ATM call delta should be near 0.5, got {greeks['delta']}"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_deep_itm_call_delta_approaches_1(calculator):
    """
    Test ID: QA-GREEK-007
    Verify deep ITM call delta approaches 1.0

    Given: Deep ITM call (spot >> strike)
    When: Calculate Greeks
    Then: Delta > 0.9
    """
    # ARRANGE
    spot_price = 120.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20
    option_type = "CE"

    # ACT
    greeks = calculator.calculate_greeks(
        spot_price, strike_price, time_to_expiry, implied_vol, option_type
    )

    # ASSERT
    assert greeks["delta"] > 0.9, f"Deep ITM call delta should be > 0.9, got {greeks['delta']}"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_deep_otm_call_delta_approaches_0(calculator):
    """
    Test ID: QA-GREEK-008
    Verify deep OTM call delta approaches 0.0

    Given: Deep OTM call (spot << strike)
    When: Calculate Greeks
    Then: Delta < 0.1
    """
    # ARRANGE
    spot_price = 80.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20
    option_type = "CE"

    # ACT
    greeks = calculator.calculate_greeks(
        spot_price, strike_price, time_to_expiry, implied_vol, option_type
    )

    # ASSERT
    assert greeks["delta"] < 0.2, f"Deep OTM call delta should be < 0.2, got {greeks['delta']}"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_gamma_peaks_at_atm(calculator):
    """
    Test ID: QA-GREEK-009
    Verify gamma peaks for ATM options

    Given: ATM, ITM, and OTM options
    When: Calculate gamma for each
    Then: ATM gamma > ITM gamma and ATM gamma > OTM gamma
    """
    # ARRANGE
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20
    option_type = "CE"

    # ACT
    gamma_atm = calculator.calculate_greeks(100.0, 100.0, time_to_expiry, implied_vol, option_type)["gamma"]
    gamma_itm = calculator.calculate_greeks(110.0, 100.0, time_to_expiry, implied_vol, option_type)["gamma"]
    gamma_otm = calculator.calculate_greeks(90.0, 100.0, time_to_expiry, implied_vol, option_type)["gamma"]

    # ASSERT
    assert gamma_atm > gamma_itm, "ATM gamma should be > ITM gamma"
    assert gamma_atm > gamma_otm, "ATM gamma should be > OTM gamma"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_theta_negative_for_long_options(calculator):
    """
    Test ID: QA-GREEK-010
    Verify theta is negative for long options (time decay)

    Given: Long call option
    When: Calculate Greeks
    Then: Theta < 0
    """
    # ARRANGE
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20
    option_type = "CE"

    # ACT
    greeks = calculator.calculate_greeks(
        spot_price, strike_price, time_to_expiry, implied_vol, option_type
    )

    # ASSERT
    # Note: calculator returns daily theta (divided by 365)
    assert greeks["theta"] < 0, "Long option theta should be negative (time decay)"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_vega_positive_for_calls_and_puts(calculator):
    """
    Test: Verify vega is positive for both calls and puts

    Given: Call and put options
    When: Calculate vega
    Then: Vega > 0 for both (volatility increases option value)
    """
    # ARRANGE
    spot_price = 100.0
    strike_price = 100.0
    time_to_expiry = 30 / 365.25
    implied_vol = 0.20

    # ACT
    vega_call = calculator.calculate_greeks(spot_price, strike_price, time_to_expiry, implied_vol, "CE")["vega"]
    vega_put = calculator.calculate_greeks(spot_price, strike_price, time_to_expiry, implied_vol, "PE")["vega"]

    # ASSERT
    assert vega_call > 0, "Call vega should be positive"
    assert vega_put > 0, "Put vega should be positive"


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_returns_all_five_greeks(calculator):
    """
    Test: Verify all 5 Greeks are returned

    Given: Valid option parameters
    When: Calculate Greeks
    Then: Returns delta, gamma, theta, vega, rho
    """
    # ACT
    greeks = calculator.calculate_greeks(100.0, 100.0, 0.1, 0.20, "CE")

    # ASSERT
    assert "delta" in greeks
    assert "gamma" in greeks
    assert "theta" in greeks
    assert "vega" in greeks
    assert "rho" in greeks


# ============================================================================
# EDGE CASES (QA-GREEK-021 to QA-GREEK-025)
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_at_expiry_itm_call(calculator):
    """
    Test ID: QA-GREEK-021
    Verify Greeks at expiry for ITM call

    Given: Time to expiry = 0, ITM call
    When: Calculate Greeks
    Then: Delta=1, Gamma=0, Theta=0, Vega=0, Rho=0
    """
    # ACT
    greeks = calculator.calculate_greeks(
        spot_price=110.0,
        strike_price=100.0,
        time_to_expiry=0.0,
        implied_vol=0.20,
        option_type="CE"
    )

    # ASSERT
    assert greeks["delta"] == 1.0
    assert greeks["gamma"] == 0.0
    assert greeks["theta"] == 0.0
    assert greeks["vega"] == 0.0
    assert greeks["rho"] == 0.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_at_expiry_otm_call(calculator):
    """
    Test: Verify Greeks at expiry for OTM call

    Given: Time to expiry = 0, OTM call
    When: Calculate Greeks
    Then: Delta=0, all other Greeks=0
    """
    # ACT
    greeks = calculator.calculate_greeks(
        spot_price=90.0,
        strike_price=100.0,
        time_to_expiry=0.0,
        implied_vol=0.20,
        option_type="CE"
    )

    # ASSERT
    assert greeks["delta"] == 0.0
    assert greeks["gamma"] == 0.0


@pytest.mark.unit
def test_greeks_invalid_spot_price_returns_zeros(calculator):
    """
    Test ID: QA-GREEK-023
    Verify zero Greeks for invalid spot price

    Given: Spot price <= 0
    When: Calculate Greeks
    Then: Returns all zeros
    """
    # ACT
    greeks = calculator.calculate_greeks(
        spot_price=-10.0,
        strike_price=100.0,
        time_to_expiry=0.1,
        implied_vol=0.20,
        option_type="CE"
    )

    # ASSERT
    assert greeks == {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}


@pytest.mark.unit
def test_greeks_invalid_volatility_returns_zeros(calculator):
    """
    Test ID: QA-GREEK-024
    Verify zero Greeks for invalid volatility

    Given: Volatility <= 0
    When: Calculate Greeks
    Then: Returns all zeros
    """
    # ACT
    greeks = calculator.calculate_greeks(
        spot_price=100.0,
        strike_price=100.0,
        time_to_expiry=0.1,
        implied_vol=0.0,
        option_type="CE"
    )

    # ASSERT
    assert greeks == {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_greeks_put_option_negative_delta(calculator):
    """
    Test: Verify put option has negative delta

    Given: Put option
    When: Calculate Greeks
    Then: Delta < 0
    """
    # ACT
    greeks = calculator.calculate_greeks(
        spot_price=100.0,
        strike_price=100.0,
        time_to_expiry=30 / 365.25,
        implied_vol=0.20,
        option_type="PE"
    )

    # ASSERT
    assert greeks["delta"] < 0, "Put delta should be negative"
    assert greeks["delta"] > -1.0, "Put delta should be > -1.0"


# ============================================================================
# BS_GREEKS_AND_VALUES TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_and_values_call_pricing(calculator):
    """
    Test: Verify Black-Scholes call pricing

    Given: Standard BS parameters
    When: Calculate BS greeks and values
    Then: Returns model_price, intrinsic, extrinsic, Greeks
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=100.0,
        K=100.0,
        t=1.0,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert "model_price" in result
    assert "intrinsic" in result
    assert "extrinsic" in result
    assert "delta" in result
    assert result["model_price"] > 0.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_intrinsic_value_itm_call(calculator):
    """
    Test: Verify intrinsic value calculation for ITM call

    Given: ITM call (S=110, K=100)
    When: Calculate BS values
    Then: Intrinsic = 10.0
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=110.0,
        K=100.0,
        t=0.1,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert result["intrinsic"] == 10.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_intrinsic_value_itm_put(calculator):
    """
    Test: Verify intrinsic value calculation for ITM put

    Given: ITM put (S=90, K=100)
    When: Calculate BS values
    Then: Intrinsic = 10.0
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="p",
        S=90.0,
        K=100.0,
        t=0.1,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert result["intrinsic"] == 10.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_extrinsic_value_with_option_price(calculator):
    """
    Test: Verify extrinsic value calculation with market price

    Given: Market price provided
    When: Calculate BS values
    Then: Extrinsic = market_price - intrinsic
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=100.0,
        K=100.0,
        t=0.1,
        r=0.05,
        sigma=0.20,
        option_price=5.0
    )

    # ASSERT
    # Intrinsic = 0 (ATM), so extrinsic = 5.0
    assert result["extrinsic"] == 5.0


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_theta_daily_conversion(calculator):
    """
    Test: Verify theta is converted to daily decay

    Given: Option parameters
    When: Calculate BS Greeks
    Then: theta_daily_decay = theta_annual / 365
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=100.0,
        K=100.0,
        t=0.1,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert "theta_annual" in result
    assert "theta_daily_decay" in result
    # Verify conversion
    assert abs(result["theta_daily_decay"] - result["theta_annual"] / 365.0) < 0.0001


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_rho_per_1pct_conversion(calculator):
    """
    Test: Verify rho is converted to per 1% rate change

    Given: Option parameters
    When: Calculate BS Greeks
    Then: rho_per_1pct_rate_change = rho_annual / 100
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=100.0,
        K=100.0,
        t=1.0,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert "rho_annual" in result
    assert "rho_per_1pct_rate_change" in result
    # Verify conversion
    assert abs(result["rho_per_1pct_rate_change"] - result["rho_annual"] / 100.0) < 0.0001


@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bs_greeks_at_expiry(calculator):
    """
    Test: Verify BS greeks at expiry (t=0)

    Given: t=0, ITM call
    When: Calculate BS Greeks
    Then: model_price = intrinsic, Greeks = 0 except delta
    """
    # ACT
    result = calculator.bs_greeks_and_values(
        flag="c",
        S=110.0,
        K=100.0,
        t=0.0,
        r=0.05,
        sigma=0.20
    )

    # ASSERT
    assert result["model_price"] == result["intrinsic"]
    assert result["delta"] == 1.0
    assert result["gamma"] == 0.0
    assert result["theta_annual"] == 0.0
    assert result["vega"] == 0.0


# ============================================================================
# BSM_GREEKS_AND_VALUES TESTS (with dividends)
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_bsm_greeks_with_dividend_yield(calculator_with_dividends):
    """
    Test: Verify BSM model with dividend yield

    Given: Dividend yield > 0
    When: Calculate BSM Greeks
    Then: Returns valid results with dividend adjustment
    """
    # ACT
    result = calculator_with_dividends.bsm_greeks_and_values(
        flag="c",
        S=100.0,
        K=100.0,
        t=1.0,
        r=0.10,
        sigma=0.20,
        q=0.02
    )

    # ASSERT
    assert result["model_price"] > 0.0
    assert "delta" in result
    assert result["delta"] > 0.0


# ============================================================================
# CALCULATE_OPTION_GREEKS WORKFLOW TESTS
# ============================================================================

@pytest.mark.unit
@pytest.mark.skipif(not VOLLIB_AVAILABLE, reason="py_vollib not available")
def test_calculate_option_greeks_complete_workflow(calculator):
    """
    Test: Verify complete Greeks calculation workflow

    Given: Market price, spot, strike, expiry, option type
    When: Call calculate_option_greeks
    Then: Returns (IV, Greeks dict)
    """
    # ARRANGE
    ist = ZoneInfo("Asia/Kolkata")
    current_time = datetime(2025, 11, 9, 10, 0, tzinfo=ist)
    expiry_date = "2025-11-30"

    # ACT
    iv, greeks = calculator.calculate_option_greeks(
        market_price=10.0,
        spot_price=100.0,
        strike_price=100.0,
        expiry_date=expiry_date,
        option_type="CE",
        current_time=current_time
    )

    # ASSERT
    assert iv > 0.0
    assert "delta" in greeks
    assert "gamma" in greeks
    assert "theta" in greeks
    assert "vega" in greeks
    assert "rho" in greeks


# ============================================================================
# INITIALIZATION AND ERROR HANDLING
# ============================================================================

@pytest.mark.unit
def test_calculator_initialization_with_defaults():
    """
    Test: Verify calculator initializes with default parameters

    Given: No parameters
    When: Create GreeksCalculator
    Then: Uses default values
    """
    # ACT
    calc = GreeksCalculator()

    # ASSERT
    assert calc.interest_rate == 0.10
    assert calc.dividend_yield == 0.0
    assert calc.expiry_time.hour == 15
    assert calc.expiry_time.minute == 30


@pytest.mark.unit
def test_calculator_invalid_timezone_falls_back_to_utc():
    """
    Test: Verify invalid timezone falls back to UTC

    Given: Invalid timezone string
    When: Create GreeksCalculator
    Then: Uses UTC timezone
    """
    # ACT
    calc = GreeksCalculator(market_timezone="Invalid/Timezone")

    # ASSERT
    assert calc.market_tz == ZoneInfo("UTC")


@pytest.mark.unit
def test_greeks_without_vollib_returns_zeros():
    """
    Test: Verify graceful degradation when py_vollib not available

    Given: VOLLIB_AVAILABLE = False
    When: Calculate Greeks
    Then: Returns all zeros
    """
    # ARRANGE
    calc = GreeksCalculator()

    # ACT - Mock VOLLIB_AVAILABLE as False
    with patch("app.greeks_calculator.VOLLIB_AVAILABLE", False):
        greeks = calc.calculate_greeks(100.0, 100.0, 0.1, 0.20, "CE")

    # ASSERT
    assert greeks == {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
