# Implementation Prompt: Code Quality Improvements (Weeks 5-8)

**Priority**: P2 (MEDIUM - Technical Debt Reduction)
**Estimated Duration**: 3-4 weeks (1-2 engineers part-time)
**Prerequisites**: Security + Critical testing complete
**Blocking**: Not blocking production, improves maintainability

---

## Objective

Address **top 5 code quality issues** identified in Phase 3 Code Expert Review to improve maintainability, readability, and reduce technical debt.

**Issues**:
1. Giant files (fo.py: 2,146 lines, database.py: 1,914 lines)
2. Poor type hint coverage (58.1% vs target 95%+)
3. Low docstring coverage (~40% vs target 95%+)
4. N+1 query patterns in M2M worker
5. Magic numbers throughout codebase

**Success Criteria**: Code quality grade increases from B- to A, maintainability improved by 50%.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Reference**: `/docs/assessment_1/phase3_code_expert_review.md`
**Current Code Quality Grade**: B- (72/100)
**Target Code Quality Grade**: A (90/100)

---

## Task 1: Split Giant Files - Week 1 (8-12 hours)

### 1.1: Refactor app/routes/fo.py (2,146 lines → 4 modules)

**Current State**: Single file with 21 route handlers

**Target Structure**:
```
app/routes/fo/
├── __init__.py          # Re-export all routes
├── rest.py              # REST endpoints (500 lines)
├── websocket.py         # WebSocket endpoints (400 lines)
├── helpers.py           # Utility functions (300 lines)
└── services.py          # Business logic (600 lines)
```

**Step 1.1.1: Create directory structure**
```bash
mkdir -p /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/routes/fo
```

**Step 1.1.2: Split REST endpoints**
```python
# app/routes/fo/rest.py - NEW FILE
"""F&O REST API endpoints."""
from fastapi import APIRouter, HTTPException, Depends
from app.dependencies import DbPool, RedisClient
import logging

router = APIRouter(prefix="/fo", tags=["F&O Analytics"])
logger = logging.getLogger(__name__)

# Move REST endpoints here:
# - GET /fo/strike-distribution
# - GET /fo/oi-change
# - GET /fo/moneyness-series
# - GET /fo/instruments/fo-enabled
# ... (12 REST endpoints)
```

**Step 1.1.3: Split WebSocket endpoints**
```python
# app/routes/fo/websocket.py - NEW FILE
"""F&O WebSocket streaming endpoints."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.dependencies import verify_websocket_token
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Move WebSocket endpoints here:
# - WS /ws/fo/stream
# - WS /ws/fo/greeks
# ... (3 WebSocket endpoints)
```

**Step 1.1.4: Extract business logic**
```python
# app/routes/fo/services.py - NEW FILE
"""F&O business logic and data processing."""
from typing import List, Dict
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

async def calculate_strike_distribution(
    pool,
    symbol: str,
    expiry: str
) -> Dict:
    """
    Calculate strike distribution for F&O options.

    Args:
        pool: Database connection pool
        symbol: Underlying symbol (NIFTY, BANKNIFTY)
        expiry: Expiry date (YYYY-MM-DD)

    Returns:
        Strike distribution with OI, volume, Greeks
    """
    # Move complex business logic here
    pass
```

**Step 1.1.5: Extract utilities**
```python
# app/routes/fo/helpers.py - NEW FILE
"""F&O utility functions."""
from typing import Optional
from datetime import datetime

def format_expiry_label(expiry_date: datetime) -> str:
    """Format expiry date as label (e.g., '09 May')."""
    return expiry_date.strftime("%d %b")

def calculate_moneyness(strike: float, spot: float) -> str:
    """Calculate moneyness category (ITM, ATM, OTM)."""
    if abs(strike - spot) < spot * 0.01:  # Within 1%
        return "ATM"
    elif strike < spot:
        return "ITM" if is_call else "OTM"
    else:
        return "OTM" if is_call else "ITM"
```

**Step 1.1.6: Update __init__.py to re-export**
```python
# app/routes/fo/__init__.py - NEW FILE
"""F&O routes package."""
from app.routes.fo.rest import router as rest_router
from app.routes.fo.websocket import router as ws_router

# Combine routers
__all__ = ["rest_router", "ws_router"]
```

**Step 1.1.7: Update app/main.py**
```python
# app/main.py - UPDATE
from app.routes.fo import rest_router, ws_router

# Replace single router with split routers
app.include_router(rest_router)
app.include_router(ws_router)
```

**Validation**:
- [ ] All REST endpoints functional
- [ ] All WebSocket endpoints functional
- [ ] Zero functional regression
- [ ] File sizes: rest.py <500 lines, websocket.py <400 lines

**Effort**: 8-12 hours

---

### 1.2: Refactor app/database.py (1,914 lines → 3 modules)

**Current State**: Single file with connection pooling + query functions

**Target Structure**:
```
app/database/
├── __init__.py          # Re-export
├── pool.py              # Connection pool management (200 lines)
├── queries.py           # Reusable query functions (800 lines)
└── utils.py             # Database utilities (100 lines)
```

**Validation**:
- [ ] All database operations functional
- [ ] Connection pool works correctly
- [ ] Zero functional regression

**Effort**: 6-8 hours

---

## Task 2: Add Type Hints (58% → 95%) - Week 2 (10-15 hours)

### Current State

**Type Hint Coverage**: 58.1% (1,432 / 2,464 functions)

**Missing Type Hints**:
```python
# app/routes/fo.py - CURRENT (NO TYPE HINTS)
async def get_strike_distribution(symbol, expiry):  # ❌ No types
    results = await fetch_data(symbol, expiry)
    return results
```

### Target State

**Type Hint Coverage**: 95%+

```python
# app/routes/fo/rest.py - FIXED (FULL TYPE HINTS)
from typing import Dict, List, Optional
from datetime import date
from decimal import Decimal

async def get_strike_distribution(
    symbol: str,
    expiry: date,
    pool: DbPool
) -> Dict[str, any]:
    """
    Get strike distribution for F&O options.

    Args:
        symbol: Underlying symbol (NIFTY, BANKNIFTY)
        expiry: Expiry date
        pool: Database connection pool

    Returns:
        Strike distribution with OI, volume, Greeks
    """
    results: List[Dict] = await fetch_data(symbol, expiry, pool)
    return {"strikes": results}
```

### Implementation Steps

**Step 2.1: Add type hints to functions (priority order)**

1. **Public API routes** (highest priority): 100+ functions
2. **Business logic functions**: 80+ functions
3. **Database query functions**: 120+ functions
4. **Utility functions**: 50+ functions

**Step 2.2: Use mypy for validation**
```bash
# Install mypy
pip install mypy==1.5.1
echo "mypy==1.5.1" >> requirements.txt

# Create mypy.ini
cat > mypy.ini << 'EOF'
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True  # Enforce type hints
ignore_missing_imports = True

# Exclude test files
[mypy-tests.*]
ignore_errors = True
EOF

# Run mypy
mypy app/

# Fix errors until clean
```

**Step 2.3: Add to CI/CD**
```yaml
# .github/workflows/test.yml - ADD MYPY STEP
- name: Run mypy type checker
  run: |
    mypy app/ --strict
```

**Validation**:
- [ ] Type hint coverage ≥95%
- [ ] mypy passes with --strict
- [ ] CI/CD enforces type hints

**Effort**: 10-15 hours (distributed across codebase)

---

## Task 3: Add Docstrings (40% → 95%) - Week 3 (10-15 hours)

### Current State

**Docstring Coverage**: ~40%

**Missing Docstrings**:
```python
# app/routes/fo.py - CURRENT (NO DOCSTRING)
async def calculate_net_greeks(positions):  # ❌ No docstring
    delta = sum(p["delta"] * p["qty"] for p in positions)
    return delta
```

### Target State

**Docstring Coverage**: 95%+

```python
# app/routes/fo/services.py - FIXED (GOOGLE-STYLE DOCSTRING)
async def calculate_net_greeks(
    positions: List[Dict],
    pool: DbPool
) -> Dict[str, Decimal]:
    """
    Calculate net Greeks for a portfolio of option positions.

    Weighted Greeks formula:
        Net Delta = Σ(delta × qty × lot_size × direction_multiplier)

    Args:
        positions: List of option positions with instrument data
        pool: Database connection pool for fetching lot sizes

    Returns:
        Dictionary with net Greeks:
            {
                "net_delta": Decimal("123.45"),
                "net_gamma": Decimal("0.50"),
                "net_theta": Decimal("-12.30"),
                "net_vega": Decimal("45.67")
            }

    Raises:
        ValueError: If positions list is empty
        HTTPException: If instrument data not found

    Example:
        >>> positions = [
        ...     {"tradingsymbol": "NIFTY2550024000CE", "delta": 0.5, "qty": 75}
        ... ]
        >>> greeks = await calculate_net_greeks(positions, pool)
        >>> print(greeks["net_delta"])
        Decimal("37.50")
    """
    if not positions:
        raise ValueError("Positions list cannot be empty")

    net_delta = sum(
        p["delta"] * p["qty"] * p.get("lot_size", 1) * (1 if p["direction"] == "BUY" else -1)
        for p in positions
    )

    return {
        "net_delta": Decimal(str(net_delta)),
        "net_gamma": Decimal("0.00"),  # Calculate gamma
        "net_theta": Decimal("0.00"),  # Calculate theta
        "net_vega": Decimal("0.00")    # Calculate vega
    }
```

### Implementation Steps

**Step 3.1: Add docstrings (priority order)**

1. **Public API routes** (highest priority): 100+ functions
2. **Business logic functions**: 80+ functions
3. **Complex algorithms**: 30+ functions
4. **Database queries**: 50+ functions

**Step 3.2: Use pydocstyle for validation**
```bash
# Install pydocstyle
pip install pydocstyle==6.3.0
echo "pydocstyle==6.3.0" >> requirements.txt

# Create .pydocstyle
cat > .pydocstyle << 'EOF'
[pydocstyle]
convention = google
match = (?!test_).*\.py
match-dir = (?!migrations|tests|alembic).*
EOF

# Run pydocstyle
pydocstyle app/

# Fix errors until clean
```

**Validation**:
- [ ] Docstring coverage ≥95%
- [ ] pydocstyle passes
- [ ] All public APIs documented

**Effort**: 10-15 hours

---

## Task 4: Fix N+1 Query Patterns - Week 4 (6-8 hours)

### Background

**N+1 Query Anti-Pattern**: Looping over items and querying database for each

**Example (CURRENT - BAD)**:
```python
# app/workers/strategy_m2m_worker.py - N+1 QUERY PATTERN
strategies = await conn.fetch("SELECT * FROM strategies")  # 1 query

for strategy in strategies:  # N queries
    instruments = await conn.fetch("""
        SELECT * FROM strategy_instruments WHERE strategy_id = $1
    """, strategy['id'])

    # Process instruments...
```

**Total Queries**: 1 + N (if 100 strategies → 101 queries)

### Fixed Version

```python
# app/workers/strategy_m2m_worker.py - FIXED (SINGLE QUERY)
strategies_with_instruments = await conn.fetch("""
    SELECT
        s.id AS strategy_id,
        s.name,
        json_agg(
            json_build_object(
                'instrument_token', si.instrument_token,
                'tradingsymbol', si.tradingsymbol,
                'direction', si.direction,
                'quantity', si.quantity,
                'entry_price', si.entry_price
            )
        ) AS instruments
    FROM strategies s
    LEFT JOIN strategy_instruments si ON si.strategy_id = s.id
    WHERE s.status = 'active'
      AND si.exit_time IS NULL
    GROUP BY s.id, s.name
""")

# Process all strategies in memory (1 query total)
for row in strategies_with_instruments:
    strategy_id = row['strategy_id']
    instruments = row['instruments']  # Already fetched
    # Process instruments...
```

**Total Queries**: 1 (90% faster)

### Implementation Steps

**Step 4.1: Find all N+1 patterns**
```bash
# Search for loop-inside-query patterns
grep -rn "for .* in" app/ --include="*.py" | grep -A5 "await.*fetch"
```

**Step 4.2: Fix using JOIN or json_agg**

**Validation**:
- [ ] All N+1 patterns eliminated
- [ ] Query count reduced by 80-90%
- [ ] Performance benchmarks improved

**Effort**: 6-8 hours

---

## Task 5: Eliminate Magic Numbers - Week 4 (4-6 hours)

### Background

**Magic Numbers**: Hardcoded values with no explanation

**Examples (CURRENT - BAD)**:
```python
# app/routes/fo.py
await asyncio.sleep(30)  # ❌ What is 30?
if oi_change > 0.25:     # ❌ What is 0.25?
limit = min(limit, 100)  # ❌ What is 100?
```

### Fixed Version

```python
# app/config.py - ADD CONSTANTS
class Settings(BaseSettings):
    # ... existing fields ...

    # Cache settings
    CACHE_TTL_SECONDS: int = Field(default=30, description="Cache TTL in seconds")

    # Query limits
    MAX_API_LIMIT: int = Field(default=100, description="Maximum items per API request")
    DEFAULT_API_LIMIT: int = Field(default=50, description="Default items per API request")

    # F&O thresholds
    OI_CHANGE_THRESHOLD: float = Field(default=0.25, description="OI change threshold (25%)")
    MONEYNESS_ATM_RANGE: float = Field(default=0.01, description="ATM range (1% of spot)")

    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = Field(default=30, description="WebSocket heartbeat interval (seconds)")
    WS_MESSAGE_RATE_LIMIT: int = Field(default=100, description="Max WS messages per second")

# app/routes/fo/rest.py - USE CONSTANTS
from app.config import settings

await asyncio.sleep(settings.CACHE_TTL_SECONDS)  # ✅ Clear meaning
if oi_change > settings.OI_CHANGE_THRESHOLD:     # ✅ Clear meaning
limit = min(limit, settings.MAX_API_LIMIT)       # ✅ Clear meaning
```

### Implementation Steps

**Step 5.1: Find all magic numbers**
```bash
# Search for numeric literals
grep -rn "[^a-zA-Z][0-9][0-9]" app/ --include="*.py" | grep -v "test_"
```

**Step 5.2: Move to Settings class**

**Validation**:
- [ ] All magic numbers replaced with named constants
- [ ] Constants documented in Settings class
- [ ] Configuration centralized

**Effort**: 4-6 hours

---

## Final Checklist

### Code Quality Improvements
- [ ] **Task 1**: Giant files split (fo.py, database.py)
- [ ] **Task 2**: Type hints added (58% → 95%)
- [ ] **Task 3**: Docstrings added (40% → 95%)
- [ ] **Task 4**: N+1 query patterns fixed
- [ ] **Task 5**: Magic numbers eliminated

### Zero Regression Validation
- [ ] All existing API endpoints functional
- [ ] All existing tests pass
- [ ] Performance not degraded (benchmark tests)

### Code Quality Metrics
- [ ] Type hint coverage: ≥95% (mypy --strict passes)
- [ ] Docstring coverage: ≥95% (pydocstyle passes)
- [ ] File sizes: All files <1,000 lines
- [ ] Query efficiency: N+1 patterns eliminated

### CI/CD Integration
- [ ] mypy type checking in CI/CD
- [ ] pydocstyle in CI/CD
- [ ] Code quality gates enforced

---

## Success Metrics

**Before (Phase 3 Code Expert Review)**:
- Code Quality Grade: B- (72/100)
- Type hints: 58.1%
- Docstrings: ~40%
- Giant files: 2 files (>2,000 lines)
- N+1 patterns: 5+ instances

**After (Target)**:
- Code Quality Grade: A (90/100)
- Type hints: 95%+
- Docstrings: 95%+
- Giant files: 0 (all <1,000 lines)
- N+1 patterns: 0 (eliminated)

---

## Next Steps

1. **Ongoing**: Maintain code quality standards (enforce in CI/CD)
2. **Future**: Add code complexity analysis (radon, pylint)
3. **Future**: Implement pre-commit hooks (black, isort, flake8)

---

**Estimated Effort**: 3-4 weeks (part-time, 1-2 engineers)
**Priority**: P2 - MEDIUM (Technical Debt)
**Impact**: HIGH - Improves maintainability by 50%

---

**Last Updated**: 2025-11-09
**Owner**: Backend Team
**Next Review**: After implementation complete
