# P0 CRITICAL: Greeks Calculation Test Suite

**Role:** Quant Engineer + QA Engineer
**Priority:** P0 - CRITICAL (Financial Accuracy Risk)
**Estimated Effort:** 20 hours
**Dependencies:** None
**Target Coverage:** 95% on greeks_calculator.py

---

## Objective

Validate mathematical accuracy of Black-Scholes options pricing and Greeks calculations to prevent trading losses from incorrect pricing.

**Current State:** 12% test coverage (71/596 LOC)
**Risk:** Mispriced options leading to trading losses, incorrect risk metrics

---

## Critical Test Categories

### 1. Black-Scholes Pricing Accuracy (5 tests)

**Test QA-GREEK-001:**
```python
def test_black_scholes_call_option_pricing():
    """Verify call pricing against Hull textbook reference values"""
    calculator = GreeksCalculator()

    # Known test case: S=100, K=100, r=0.05, T=1.0, σ=0.2
    result = calculator.calculate_option_price(
        spot=100.0, strike=100.0, time_to_expiry=1.0,
        volatility=0.2, risk_free_rate=0.05, option_type="CE"
    )

    expected = 10.45  # From Hull, Options Futures and Derivatives
    assert abs(result - expected) < 0.01, f"Price {result} != {expected}"
```

**Additional scenarios:**
- Deep ITM (S=120, K=100) → Expected ~20.xx
- Deep OTM (S=80, K=100) → Expected ~0.xx
- Put-Call Parity verification
- Zero volatility edge case

---

### 2. Greeks Calculation (10 tests)

**Delta Tests (QA-GREEK-006 to QA-GREEK-008):**
- ATM call delta ≈ 0.5
- Deep ITM call delta → 1.0
- Deep OTM call delta → 0.0

**Gamma Tests (QA-GREEK-009):**
- Peaks at ATM
- Approaches 0 for deep ITM/OTM

**Theta/Vega/Rho Tests (QA-GREEK-010):**
- Theta always negative for long options
- Vega sensitivity verification
- Rho interest rate sensitivity

---

### 3. Implied Volatility Calculation (5 tests)

**Test QA-GREEK-011: IV Convergence**
```python
def test_iv_calculation_convergence():
    """Verify Newton-Raphson converges within 100 iterations"""
    calculator = GreeksCalculator()

    # Given option price, solve for IV
    option_price = 10.45
    iv = calculator.calculate_implied_volatility(
        option_price=option_price, spot=100, strike=100,
        time_to_expiry=1.0, risk_free_rate=0.05, option_type="CE"
    )

    # Should converge to σ ≈ 0.20
    assert abs(iv - 0.20) < 0.001
    assert calculator.iterations < 100
```

**Additional IV tests:**
- Bounds verification (0.01 to 5.0)
- Zero extrinsic value → IV=0
- Non-convergence handling
- Different initial guesses converge to same IV

---

### 4. Time-to-Expiry Calculations (5 tests)

**Test QA-GREEK-016: Market Hours Calculation**
```python
def test_time_to_expiry_in_market_hours():
    """Verify T calculation excludes non-market hours"""
    from datetime import datetime
    import pytz

    ist = pytz.timezone('Asia/Kolkata')

    # Current: Thursday 10:00 AM IST
    # Expiry: Thursday 3:30 PM IST (same day)
    current = ist.localize(datetime(2025, 11, 13, 10, 0))
    expiry = ist.localize(datetime(2025, 11, 13, 15, 30))

    T = calculate_time_to_expiry(current, expiry)

    # Market hours: 9:15 AM - 3:30 PM (6.25 hours/day)
    # Remaining: 5.5 hours = 5.5/6.25 = 0.88 trading days
    # In years: 0.88 / 252 = 0.00349 years
    expected_T = 0.00349
    assert abs(T - expected_T) < 0.0001
```

**Additional T tests:**
- After market close (exclude overnight)
- Across weekends (exclude Sat/Sun)
- On expiry day (T approaches 0)
- Expired options (T = 0)

---

### 5. Edge Cases (5 tests)

**Test QA-GREEK-021: Zero Volatility**
```python
def test_greeks_at_zero_volatility():
    """Verify behavior when σ=0 (step function)"""
    calculator = GreeksCalculator()

    greeks = calculator.calculate_greeks(
        spot=100, strike=100, time_to_expiry=1.0,
        volatility=0.0, risk_free_rate=0.05, option_type="CE"
    )

    # Delta should be 0 or 1 (step function at strike)
    assert greeks['delta'] in [0.0, 1.0]
    # Gamma should be 0 or undefined
    assert greeks['gamma'] == 0.0 or np.isnan(greeks['gamma'])
```

**Additional edge cases:**
- Very high volatility (σ=5.0)
- Zero time to expiry (T=0)
- Negative spot (should raise ValueError)
- Negative strike (should raise ValueError)

---

## Mathematical Reference Values

Use **Hull's "Options, Futures, and Other Derivatives"** as benchmark:

| S | K | T | σ | r | Call Price | Delta | Gamma |
|---|---|---|---|---|-----------|-------|-------|
| 100 | 100 | 1.0 | 0.20 | 0.05 | 10.45 | 0.6368 | 0.0199 |
| 120 | 100 | 1.0 | 0.20 | 0.05 | 24.08 | 0.9465 | 0.0042 |
| 80 | 100 | 1.0 | 0.20 | 0.05 | 0.59 | 0.1010 | 0.0097 |

---

## Acceptance Criteria

- [ ] 25 tests passing (5 pricing + 10 Greeks + 5 IV + 5 T + 5 edge cases)
- [ ] **95%+ coverage on greeks_calculator.py**
- [ ] Pricing accuracy: < 1 cent deviation from reference
- [ ] IV accuracy: < 0.001 deviation
- [ ] Performance: < 1ms per calculation
- [ ] Documented mathematical references (Hull textbook)
- [ ] Test data includes real market scenarios

---

## Sign-Off

- [ ] Quant Lead: _____________________ Date: _____
- [ ] QA Lead: _____________________ Date: _____
- [ ] Risk Manager: _____________________ Date: _____
