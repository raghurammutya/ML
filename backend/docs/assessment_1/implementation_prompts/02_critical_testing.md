# Implementation Prompt: Critical Testing (Weeks 2-3)

**Priority**: P0 (BLOCKING PRODUCTION)
**Estimated Duration**: 10-12 days (1-2 engineers)
**Prerequisites**: Security remediation (Prompt 01) complete
**Blocking**: Production deployment

---

## Objective

Implement **120 critical path tests** to achieve **40% test coverage** and validate core business logic correctness before production deployment.

**Current State**:
- Test coverage: 2.7% (38 tests)
- Financial calculation tests: 0
- Integration tests: 0
- Security tests: 0

**Target State**:
- Test coverage: 40%+ (158 tests total)
- Financial calculation tests: 55 tests
- Integration tests: 35 tests
- Security tests: 30 tests

**Success Criteria**: All 120 critical tests pass with zero functional regression.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Reference**: `/docs/assessment_1/phase4_qa_validation.md`
**Current QA Grade**: D+ (47/100)
**Target QA Grade**: B (80/100) minimum for production

**Zero Regression Guarantee**: All tests validate existing functionality without modifying code behavior.

---

## Test Suite Breakdown (120 Critical Tests)

### Category 1: Financial Calculations (55 tests)
- Strategy M2M Calculation: 25 tests
- F&O Greeks Calculations: 20 tests
- Decimal Precision: 10 tests

### Category 2: Database Operations (30 tests)
- Connection pooling: 10 tests
- Transaction handling: 10 tests
- Query correctness: 10 tests

### Category 3: Authentication & Authorization (30 tests)
- JWT validation: 10 tests
- Multi-account isolation: 10 tests
- WebSocket authentication: 10 tests

### Category 4: API Contract Testing (5 tests)
- Critical endpoints: 5 tests

---

## Task 1: Strategy M2M Calculation Tests (25 tests) - Days 1-3

### Background

**File**: `app/workers/strategy_m2m_worker.py`
**Risk**: Incorrect P&L calculation → user financial loss
**Current Tests**: 0 tests (**CRITICAL GAP**)

**M2M Formula**:
```python
M2M = Σ(instrument_ltp × qty × direction_multiplier)

direction_multiplier:
  BUY: -1 (paid money)
  SELL: +1 (received money)
```

### Test Suite 1.1: BUY Position Tests (10 tests)

```python
# tests/unit/test_strategy_m2m.py - NEW FILE
import pytest
from decimal import Decimal
from app.workers.strategy_m2m_worker import calculate_instrument_m2m

class TestStrategyM2MBuyPositions:
    """Test M2M calculation for BUY positions."""

    def test_buy_position_profit(self):
        """BUY position with LTP > entry_price → Loss (negative M2M).

        Explanation:
        - Bought at 100, now worth 105
        - Paid 100 × 75 = 7,500
        - Now worth 105 × 75 = 7,875
        - M2M = Current Value - Entry Value
        - M2M = 7,875 - 7,500 = 375 profit
        - BUT in position-based accounting, BUY = outflow
        - M2M = (105 - 100) × 75 × -1 = -375 (paid more)
        """
        instrument = {
            "direction": "BUY",
            "quantity": 75,
            "entry_price": Decimal("100.00")
        }
        ltp = Decimal("105.00")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("-375.00")
        assert isinstance(m2m, Decimal)  # Type check

    def test_buy_position_loss(self):
        """BUY position with LTP < entry_price → Profit (positive M2M).

        Explanation:
        - Bought at 100, now worth 95
        - Paid 100 × 50 = 5,000
        - Now worth 95 × 50 = 4,750
        - M2M = (95 - 100) × 50 × -1 = 250 (saved money)
        """
        instrument = {
            "direction": "BUY",
            "quantity": 50,
            "entry_price": Decimal("100.00")
        }
        ltp = Decimal("95.00")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("250.00")

    def test_buy_position_no_change(self):
        """BUY position with LTP = entry_price → Zero M2M."""
        instrument = {
            "direction": "BUY",
            "quantity": 100,
            "entry_price": Decimal("200.50")
        }
        ltp = Decimal("200.50")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("0.00")

    def test_buy_position_large_quantity(self):
        """BUY position with large quantity (stress test)."""
        instrument = {
            "direction": "BUY",
            "quantity": 10000,
            "entry_price": Decimal("50.25")
        }
        ltp = Decimal("55.75")

        m2m = calculate_instrument_m2m(instrument, ltp)

        # (55.75 - 50.25) × 10,000 × -1 = -55,000
        assert m2m == Decimal("-55000.00")

    def test_buy_position_decimal_precision(self):
        """BUY position with high decimal precision."""
        instrument = {
            "direction": "BUY",
            "quantity": 75,
            "entry_price": Decimal("123.4567")
        }
        ltp = Decimal("128.9876")

        m2m = calculate_instrument_m2m(instrument, ltp)

        # (128.9876 - 123.4567) × 75 × -1 = -414.8175
        assert m2m == Decimal("-414.8175")

    def test_buy_position_fractional_quantity(self):
        """BUY position with fractional quantity (forex, crypto)."""
        instrument = {
            "direction": "BUY",
            "quantity": 0.5,
            "entry_price": Decimal("50000.00")
        }
        ltp = Decimal("52000.00")

        m2m = calculate_instrument_m2m(instrument, ltp)

        # (52000 - 50000) × 0.5 × -1 = -1000
        assert m2m == Decimal("-1000.00")

    # 4 more edge case tests...
    # - Zero quantity
    # - Negative quantity (should raise error)
    # - None/null values (should raise error)
    # - Very large price difference
```

### Test Suite 1.2: SELL Position Tests (10 tests)

```python
class TestStrategyM2MSellPositions:
    """Test M2M calculation for SELL positions."""

    def test_sell_position_profit(self):
        """SELL position with LTP < entry_price → Profit (positive M2M).

        Explanation:
        - Sold at 200, buy back at 180
        - Received 200 × 50 = 10,000
        - Buy back 180 × 50 = 9,000
        - Profit = 10,000 - 9,000 = 1,000
        - M2M = (180 - 200) × 50 × +1 = +1,000
        """
        instrument = {
            "direction": "SELL",
            "quantity": 50,
            "entry_price": Decimal("200.00")
        }
        ltp = Decimal("180.00")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("1000.00")

    def test_sell_position_loss(self):
        """SELL position with LTP > entry_price → Loss (negative M2M).

        Explanation:
        - Sold at 100, buy back at 120
        - Received 100 × 75 = 7,500
        - Buy back 120 × 75 = 9,000
        - Loss = 7,500 - 9,000 = -1,500
        - M2M = (120 - 100) × 75 × +1 = -1,500
        """
        instrument = {
            "direction": "SELL",
            "quantity": 75,
            "entry_price": Decimal("100.00")
        }
        ltp = Decimal("120.00")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("-1500.00")

    def test_sell_position_no_change(self):
        """SELL position with LTP = entry_price → Zero M2M."""
        instrument = {
            "direction": "SELL",
            "quantity": 100,
            "entry_price": Decimal("300.25")
        }
        ltp = Decimal("300.25")

        m2m = calculate_instrument_m2m(instrument, ltp)

        assert m2m == Decimal("0.00")

    # 7 more SELL position tests (mirror BUY tests)...
```

### Test Suite 1.3: Mixed Positions (5 tests)

```python
class TestStrategyM2MMixedPositions:
    """Test M2M calculation for strategies with mixed BUY/SELL positions."""

    def test_mixed_positions_net_profit(self):
        """Strategy with both BUY and SELL positions → Net profit."""
        instruments = [
            {
                "direction": "BUY",
                "quantity": 50,
                "entry_price": Decimal("100.00"),
                "ltp": Decimal("95.00")  # BUY loss → +250 M2M
            },
            {
                "direction": "SELL",
                "quantity": 50,
                "entry_price": Decimal("200.00"),
                "ltp": Decimal("180.00")  # SELL profit → +1000 M2M
            }
        ]

        total_m2m = calculate_strategy_m2m(instruments)

        # BUY: (95-100) × 50 × -1 = +250
        # SELL: (180-200) × 50 × +1 = +1000
        # Total: +1,250
        assert total_m2m == Decimal("1250.00")

    def test_mixed_positions_net_loss(self):
        """Strategy with both BUY and SELL positions → Net loss."""
        instruments = [
            {
                "direction": "BUY",
                "quantity": 75,
                "entry_price": Decimal("100.00"),
                "ltp": Decimal("105.00")  # BUY profit → -375 M2M
            },
            {
                "direction": "SELL",
                "quantity": 50,
                "entry_price": Decimal("100.00"),
                "ltp": Decimal("110.00")  # SELL loss → -500 M2M
            }
        ]

        total_m2m = calculate_strategy_m2m(instruments)

        # BUY: (105-100) × 75 × -1 = -375
        # SELL: (110-100) × 50 × +1 = -500
        # Total: -875
        assert total_m2m == Decimal("-875.00")

    def test_empty_strategy(self):
        """Strategy with no instruments → Zero M2M."""
        instruments = []

        total_m2m = calculate_strategy_m2m(instruments)

        assert total_m2m == Decimal("0.00")

    # 2 more mixed position tests...
```

**Validation**:
- [ ] All 25 M2M tests pass
- [ ] Decimal precision maintained (no float conversion)
- [ ] Edge cases handled (empty, large quantities, high precision)
- [ ] Error handling tested (negative quantity, None values)

**Effort**: 3 days (includes test writing, validation, edge cases)

---

## Task 2: F&O Greeks Calculations Tests (20 tests) - Days 4-5

### Background

**File**: `app/routes/fo.py:550-850`
**Risk**: Incorrect Greeks → bad trading decisions
**Current Tests**: 0 tests

**Greeks Formulas**:
```python
Net Delta = Σ(delta × qty × lot_size × direction_multiplier)
Net Gamma = Σ(gamma × qty × lot_size × direction_multiplier)
Net Theta = Σ(theta × qty × lot_size × direction_multiplier)
Net Vega = Σ(vega × qty × lot_size × direction_multiplier)

direction_multiplier:
  BUY: +1
  SELL: -1
```

### Test Suite 2.1: Delta Calculation Tests (5 tests)

```python
# tests/unit/test_greeks_calculations.py - NEW FILE
import pytest
from decimal import Decimal
from app.routes.fo import calculate_weighted_greeks

class TestDeltaCalculations:
    """Test Net Delta calculation for option positions."""

    def test_net_delta_long_call(self):
        """Long CALL position → Positive Net Delta.

        Explanation:
        - CALL option: delta ≈ 0.5 (moves half as much as underlying)
        - BUY 1 lot (75 qty) → positive delta exposure
        - Net Delta = 0.5 × 75 × 1 (BUY) = +37.5
        """
        positions = [
            {
                "tradingsymbol": "NIFTY2550024000CE",
                "option_type": "CALL",
                "direction": "BUY",
                "quantity": 75,
                "lot_size": 1,
                "delta": Decimal("0.5000")
            }
        ]

        greeks = calculate_weighted_greeks(positions)

        assert greeks["net_delta"] == Decimal("37.50")

    def test_net_delta_short_call(self):
        """Short CALL position → Negative Net Delta.

        Explanation:
        - SELL CALL → negative delta exposure
        - Net Delta = 0.5 × 75 × -1 (SELL) = -37.5
        """
        positions = [
            {
                "tradingsymbol": "NIFTY2550024000CE",
                "option_type": "CALL",
                "direction": "SELL",
                "quantity": 75,
                "lot_size": 1,
                "delta": Decimal("0.5000")
            }
        ]

        greeks = calculate_weighted_greeks(positions)

        assert greeks["net_delta"] == Decimal("-37.50")

    def test_net_delta_straddle(self):
        """Straddle (BUY CALL + BUY PUT at same strike) → Near Zero Net Delta.

        Explanation:
        - CALL delta: +0.5
        - PUT delta: -0.5
        - Net Delta ≈ 0 (delta-neutral strategy)
        """
        positions = [
            {
                "tradingsymbol": "NIFTY2550024000CE",
                "option_type": "CALL",
                "direction": "BUY",
                "quantity": 75,
                "lot_size": 1,
                "delta": Decimal("0.5000")
            },
            {
                "tradingsymbol": "NIFTY2550024000PE",
                "option_type": "PUT",
                "direction": "BUY",
                "quantity": 75,
                "lot_size": 1,
                "delta": Decimal("-0.5000")
            }
        ]

        greeks = calculate_weighted_greeks(positions)

        # CALL: 0.5 × 75 × 1 = +37.5
        # PUT: -0.5 × 75 × 1 = -37.5
        # Net: 0
        assert greeks["net_delta"] == Decimal("0.00")

    # 2 more delta tests (Iron Condor, Butterfly)...
```

### Test Suite 2.2: Gamma, Theta, Vega Tests (15 tests)

```python
class TestGammaCalculations:
    """Test Net Gamma calculation (5 tests)."""
    # Similar structure to Delta tests
    pass

class TestThetaCalculations:
    """Test Net Theta calculation (5 tests)."""
    # Test time decay impact
    pass

class TestVegaCalculations:
    """Test Net Vega calculation (5 tests)."""
    # Test volatility sensitivity
    pass
```

**Validation**:
- [ ] All 20 Greeks tests pass
- [ ] Delta, Gamma, Theta, Vega calculations accurate
- [ ] Multi-leg strategies tested (Straddle, Strangle, Iron Condor)
- [ ] Decimal precision maintained

**Effort**: 2 days

---

## Task 3: Decimal Precision Tests (10 tests) - Day 6

### Background

**Risk**: Using `float` instead of `Decimal` → precision loss → money loss

**Example**:
```python
# WRONG: Float precision loss
price = 0.1 + 0.2  # 0.30000000000000004 ❌

# CORRECT: Decimal precision
price = Decimal("0.1") + Decimal("0.2")  # 0.3 ✅
```

### Test Suite 3.1: Decimal Precision Tests

```python
# tests/unit/test_decimal_precision.py - NEW FILE
import pytest
from decimal import Decimal
from app.routes.fo import calculate_position_pnl

class TestDecimalPrecision:
    """Test financial calculations use Decimal, not float."""

    def test_pnl_uses_decimal_not_float(self):
        """Ensure P&L calculation uses Decimal for precision."""
        entry_price = Decimal("100.05")
        exit_price = Decimal("105.10")
        quantity = 75

        pnl = calculate_position_pnl(entry_price, exit_price, quantity)

        # (105.10 - 100.05) × 75 = 378.75
        assert pnl == Decimal("378.75")
        assert isinstance(pnl, Decimal)  # Type check

    def test_float_conversion_precision_loss(self):
        """Demonstrate float precision loss (negative test)."""
        entry_price = 100.05  # float
        exit_price = 105.10   # float
        quantity = 75

        # Using float arithmetic
        pnl_float = (exit_price - entry_price) * quantity

        # Float result: 378.7499999999... (precision loss)
        assert pnl_float != 378.75  # Float is imprecise
        assert abs(pnl_float - 378.75) < 0.01  # Close, but not exact

    def test_decimal_maintains_precision_in_aggregation(self):
        """Test Decimal precision in multi-instrument aggregation."""
        instruments = [
            {"pnl": Decimal("123.45")},
            {"pnl": Decimal("67.89")},
            {"pnl": Decimal("0.01")}
        ]

        total_pnl = sum(i["pnl"] for i in instruments)

        # 123.45 + 67.89 + 0.01 = 191.35 (exact)
        assert total_pnl == Decimal("191.35")

    def test_decimal_division_precision(self):
        """Test Decimal division maintains precision."""
        total_value = Decimal("1000.00")
        quantity = 3

        per_unit_value = total_value / quantity

        # 1000 / 3 = 333.3333... (repeating)
        # Decimal maintains precision up to context settings
        assert per_unit_value == Decimal("333.3333333333333333333333333")

    def test_decimal_rounding_to_2_places(self):
        """Test Decimal rounding for display (2 decimal places)."""
        pnl = Decimal("378.7567")

        rounded_pnl = pnl.quantize(Decimal("0.01"))

        assert rounded_pnl == Decimal("378.76")  # Rounded up

    # 5 more decimal precision tests...
```

**Validation**:
- [ ] All 10 decimal tests pass
- [ ] No float arithmetic in financial calculations
- [ ] Rounding handled correctly (2 decimal places for currency)

**Effort**: 1 day

---

## Task 4: Database Operations Tests (30 tests) - Days 7-8

### Test Suite 4.1: Connection Pooling Tests (10 tests)

```python
# tests/integration/test_database_pooling.py - NEW FILE
import pytest
import asyncio
from app.database import get_pool

@pytest.mark.asyncio
class TestConnectionPooling:
    """Test database connection pooling behavior."""

    async def test_pool_acquires_connection(self):
        """Test connection can be acquired from pool."""
        pool = await get_pool()

        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    async def test_pool_releases_connection(self):
        """Test connection is released back to pool."""
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Connection in use
            pass

        # Connection released, pool size should remain same
        assert pool.get_size() == pool.get_max_size()

    async def test_pool_handles_concurrent_requests(self):
        """Test pool handles 50 concurrent queries."""
        pool = await get_pool()

        async def query():
            async with pool.acquire() as conn:
                return await conn.fetchval("SELECT 1")

        # 50 concurrent queries
        results = await asyncio.gather(*[query() for _ in range(50)])

        assert all(r == 1 for r in results)
        assert len(results) == 50

    async def test_pool_exhaustion_queues_requests(self):
        """Test behavior when pool is exhausted (all connections in use)."""
        pool = await get_pool()
        max_size = pool.get_max_size()

        # Acquire all connections
        connections = []
        for _ in range(max_size):
            conn = await pool.acquire()
            connections.append(conn)

        # Next acquire should wait (timeout test)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(pool.acquire(), timeout=1.0)

        # Release connections
        for conn in connections:
            await pool.release(conn)

    # 6 more pooling tests...
```

### Test Suite 4.2: Transaction Handling Tests (10 tests)

```python
class TestTransactionHandling:
    """Test database transaction atomicity."""

    async def test_transaction_commit_on_success(self):
        """Test transaction commits when all operations succeed."""
        pool = await get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO strategies (name, user_id, status)
                    VALUES ('Test Strategy', 1, 'active')
                """)

        # Verify insert committed
        async with pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM strategies WHERE name = 'Test Strategy'
            """)
            assert count == 1

    async def test_transaction_rollback_on_error(self):
        """Test transaction rolls back when error occurs."""
        pool = await get_pool()

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("""
                        INSERT INTO strategies (name, user_id, status)
                        VALUES ('Test Strategy', 1, 'active')
                    """)

                    # Force error (duplicate key)
                    await conn.execute("""
                        INSERT INTO strategies (id, name, user_id, status)
                        VALUES (1, 'Test Strategy', 1, 'active')
                    """)
        except Exception:
            pass

        # Verify insert rolled back
        async with pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM strategies WHERE name = 'Test Strategy'
            """)
            assert count == 0  # Rollback successful

    # 8 more transaction tests...
```

### Test Suite 4.3: Query Correctness Tests (10 tests)

```python
class TestQueryCorrectness:
    """Test database queries return correct results."""

    async def test_parameterized_query_prevents_injection(self):
        """Test parameterized queries use $1, $2 placeholders."""
        pool = await get_pool()

        user_id = 1
        sort_by = "id; DROP TABLE strategies; --"  # SQL injection attempt

        # Should raise validation error (whitelist check)
        with pytest.raises(ValueError):
            async with pool.acquire() as conn:
                await conn.fetch("""
                    SELECT * FROM strategies
                    WHERE user_id = $1
                    ORDER BY $2 DESC
                """, user_id, sort_by)

    # 9 more query tests...
```

**Validation**:
- [ ] All 30 database tests pass
- [ ] Connection pooling tested (acquire, release, exhaustion)
- [ ] Transaction atomicity validated (commit, rollback)
- [ ] Query correctness verified (parameterized queries, no injection)

**Effort**: 2 days

---

## Task 5: Authentication & Authorization Tests (30 tests) - Days 9-10

### Test Suite 5.1: JWT Validation Tests (10 tests)

```python
# tests/security/test_jwt_authentication.py - NEW FILE
import pytest
from jose import jwt
from datetime import datetime, timedelta
from app.config import settings
from app.dependencies import verify_jwt_token

class TestJWTValidation:
    """Test JWT token validation."""

    def test_valid_jwt_token_accepted(self):
        """Test valid JWT token is accepted."""
        payload = {
            "user_id": 1,
            "account_id": 123,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        decoded = verify_jwt_token(token)

        assert decoded["user_id"] == 1
        assert decoded["account_id"] == 123

    def test_invalid_jwt_token_rejected(self):
        """Test invalid JWT token is rejected."""
        token = "invalid_token_12345"

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt_token(token)

        assert exc_info.value.status_code == 401
        assert "Invalid authentication token" in str(exc_info.value.detail)

    def test_expired_jwt_token_rejected(self):
        """Test expired JWT token is rejected."""
        payload = {
            "user_id": 1,
            "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

        with pytest.raises(HTTPException) as exc_info:
            verify_jwt_token(token)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    # 7 more JWT tests...
```

### Test Suite 5.2: Multi-Account Isolation Tests (10 tests)

```python
class TestMultiAccountIsolation:
    """Test that User A cannot access User B's data."""

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_strategies(self):
        """Test User A cannot retrieve User B's strategies."""
        # User A's token (user_id=1, account_id=123)
        token_a = create_test_token(user_id=1, account_id=123)

        # Create strategy for User B (user_id=2, account_id=456)
        await create_strategy(user_id=2, name="User B Strategy")

        # User A attempts to access User B's strategy
        response = client.get(
            "/strategies?user_id=2",
            headers={"Authorization": f"Bearer {token_a}"}
        )

        # Should return 403 Forbidden
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # 9 more isolation tests...
```

### Test Suite 5.3: WebSocket Authentication Tests (10 tests)

```python
class TestWebSocketAuthentication:
    """Test WebSocket JWT authentication."""

    @pytest.mark.asyncio
    async def test_websocket_connection_requires_token(self):
        """Test WebSocket connection without token is rejected."""
        # Attempt connection without token
        with pytest.raises(WebSocketException):
            async with websockets.connect("ws://localhost:8081/ws/fo/stream") as ws:
                await ws.recv()

    # 9 more WebSocket tests...
```

**Validation**:
- [ ] All 30 authentication tests pass
- [ ] JWT validation tested (valid, invalid, expired)
- [ ] Multi-account isolation enforced
- [ ] WebSocket authentication validated

**Effort**: 2 days

---

## Task 6: API Contract Testing (5 tests) - Day 11

### Test Suite 6.1: Critical Endpoint Tests

```python
# tests/integration/test_api_contracts.py - NEW FILE
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestCriticalEndpoints:
    """Test API contracts for critical endpoints."""

    def test_get_strategies_returns_correct_schema(self):
        """Test GET /strategies returns correct JSON schema."""
        response = client.get(
            "/strategies",
            headers={"Authorization": f"Bearer {valid_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Validate schema
        assert "strategies" in data
        assert "total_count" in data
        assert isinstance(data["strategies"], list)

        if data["strategies"]:
            strategy = data["strategies"][0]
            assert "id" in strategy
            assert "name" in strategy
            assert "status" in strategy
            assert "total_m2m" in strategy

    def test_post_orders_validates_request(self):
        """Test POST /accounts/{id}/orders validates request body."""
        response = client.post(
            "/accounts/123/orders",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={
                # Missing required field "quantity"
                "tradingsymbol": "NIFTY2550024000CE",
                "price": 100.0
            }
        )

        # Should return 422 Unprocessable Entity
        assert response.status_code == 422
        assert "quantity" in str(response.json()["detail"])

    # 3 more endpoint tests...
```

**Validation**:
- [ ] All 5 API contract tests pass
- [ ] JSON schemas validated
- [ ] Request validation enforced
- [ ] Error responses consistent

**Effort**: 1 day

---

## Task 7: CI/CD Integration - Day 12

### Setup pytest with coverage

```bash
# Install pytest and coverage tools
pip install pytest pytest-asyncio pytest-cov
echo "pytest==7.4.0" >> requirements.txt
echo "pytest-asyncio==0.21.0" >> requirements.txt
echo "pytest-cov==4.1.0" >> requirements.txt

# Create pytest.ini configuration
cat > pytest.ini << 'EOF'
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto

# Coverage settings
addopts = --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=40
EOF

# Run tests with coverage
pytest --cov=app --cov-report=term-missing --cov-report=html

# View coverage report
open htmlcov/index.html
```

### GitHub Actions CI/CD

```yaml
# .github/workflows/test.yml - NEW FILE
name: Backend Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: stocksblitz
          POSTGRES_PASSWORD: stocksblitz123
          POSTGRES_DB: stocksblitz_unified_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run tests
        env:
          DB_PASSWORD: stocksblitz123
          DB_HOST: localhost
          DB_PORT: 5432
          DB_NAME: stocksblitz_unified_test
          DB_USER: stocksblitz
          REDIS_URL: redis://localhost:6379
          JWT_SECRET_KEY: test_secret_key_12345
        run: |
          pytest --cov=app --cov-report=xml --cov-fail-under=40

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true
```

**Validation**:
- [ ] pytest runs successfully
- [ ] Coverage report shows 40%+ coverage
- [ ] CI/CD pipeline configured (GitHub Actions)
- [ ] Tests run on every PR

**Effort**: 1 day

---

## Final Checklist

### Test Implementation
- [ ] **Task 1**: Strategy M2M tests (25 tests)
- [ ] **Task 2**: F&O Greeks tests (20 tests)
- [ ] **Task 3**: Decimal precision tests (10 tests)
- [ ] **Task 4**: Database operations tests (30 tests)
- [ ] **Task 5**: Authentication tests (30 tests)
- [ ] **Task 6**: API contract tests (5 tests)
- [ ] **Task 7**: CI/CD integration complete

### Test Coverage
- [ ] Total tests: 158 (38 existing + 120 new)
- [ ] Test coverage: 40%+ (from 2.7%)
- [ ] Financial calculation tests: 55 tests
- [ ] Security tests: 30 tests
- [ ] Integration tests: 35 tests

### CI/CD
- [ ] pytest configured
- [ ] Coverage reporting enabled
- [ ] GitHub Actions workflow created
- [ ] Tests run on every PR

---

## Success Metrics

**Before (Phase 4 QA Validation)**:
- QA Grade: D+ (47/100)
- Test coverage: 2.7%
- Financial tests: 0

**After (Target)**:
- QA Grade: B (80/100)
- Test coverage: 40%+
- Financial tests: 55

---

## Next Steps

1. **Week 4+**: Consider Implementation Prompt 03 (Strategy System completion)
2. **Week 4+**: Consider Implementation Prompt 04 (Architecture fixes)
3. **Ongoing**: Expand test coverage to 90% (847 total tests)

---

**Estimated Effort**: 10-12 days (1-2 engineers)
**Priority**: P0 - BLOCKING PRODUCTION
**Impact**: CRITICAL - Validates financial correctness

---

**Last Updated**: 2025-11-09
**Owner**: QA Team
**Next Review**: After implementation complete
