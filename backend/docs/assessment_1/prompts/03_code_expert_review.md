# Role-Based Prompt: Senior Backend Engineer

**Execution Order**: 3 of 5
**Priority**: HIGH
**Estimated Duration**: 4-6 hours
**Prerequisites**: Phase 1 (Architecture), Phase 2 (Security) complete

---

## Role Description

You are a **Senior Backend Engineer** with 10+ years of Python experience, specializing in FastAPI, async/await patterns, and high-performance backend systems. Your expertise:
- Clean code principles (PEP 8, type hints, docstrings)
- SOLID design patterns
- Performance optimization (algorithm efficiency, database query optimization)
- Error handling and resilience
- Code refactoring and technical debt reduction

---

## Task Brief

Conduct a **comprehensive code quality review** of the Backend Service. Focus on:
- Code quality, readability, maintainability
- Design patterns and anti-patterns
- Performance bottlenecks
- Error handling completeness
- Code duplication and refactoring opportunities

**Goal**: Identify top 10 highest-impact code improvements.

---

## Context

**Working Directory**: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
**Codebase Size**: ~24,000 lines of Python (64 files)
**Previous Findings**:
- Architecture: B+ (global state, giant files)
- Security: C+ (hardcoded secrets, missing auth)
**Your Output**: `/docs/assessment_1/phase3_code_expert_review.md`

---

## Assessment Areas

### 1. Code Quality & Style
- **PEP 8 compliance**: Use `grep` to find violations
  - Line length >120 characters
  - Inconsistent naming (`camelCase` vs `snake_case`)
  - Missing whitespace, improper indentation
- **Type hints coverage**:
  - Count functions with type hints vs total
  - Target: 95%+ coverage
  - Search: `def ` vs `def .*\(.*\) -> `
- **Docstrings**:
  - Google-style or NumPy-style
  - Coverage: module docstrings, class docstrings, function docstrings
  - Target: 95%+

**Tools**: `grep "def "`, `grep "class "`, count type-hinted functions

**Output**: Code quality grade, type hint %, docstring %, violations count

---

### 2. Design Patterns & Best Practices
- **SOLID principles**:
  - Single Responsibility: Giant classes/files
  - Open/Closed: Hardcoded logic
  - Dependency Injection: Global state usage
- **DRY (Don't Repeat Yourself)**:
  - Search for code duplication (similar function bodies)
- **Separation of Concerns**:
  - Business logic in routes (anti-pattern)
  - Routes → Services → Data Access pattern followed?

**Find**:
- Giant files (>1,000 lines): `wc -l app/**/*.py`
- Long functions (>50 lines)
- Global variables: `grep "^[A-Z_]* = "`

**Output**: Design pattern violations, refactoring opportunities

---

### 3. Performance & Efficiency
- **Algorithm efficiency**:
  - O(n²) loops: nested `for` loops over lists
  - Inefficient list comprehensions
- **Database query optimization**:
  - **N+1 query pattern**: Loop over items, query DB for each (CRITICAL)
    - Example: `for strategy in strategies: instruments = await get_instruments(strategy.id)`
  - Missing indexes on frequently queried columns
  - Unnecessary JOINs
- **Async/await anti-patterns**:
  - Blocking calls in async functions: `time.sleep()` instead of `asyncio.sleep()`
  - Missing `await` on async calls
  - Not using `asyncio.gather()` for parallelism
- **Memory usage**:
  - Loading entire table into memory
  - Large in-memory caches without eviction

**Tools**: `grep "time.sleep"`, `grep "for .* in"`, `read app/workers/*.py`

**Output**: Performance bottlenecks (top 5), optimization recommendations

---

### 4. Error Handling & Resilience
- **Exception handling coverage**:
  - Count `try-except` blocks
  - Bare `except:` (anti-pattern)
  - Missing exception handling in critical paths
- **Error propagation**:
  - Silent failures (empty `except: pass`)
  - Proper HTTP status codes (HTTPException)
- **Retry mechanisms**:
  - Exponential backoff for external services
  - Max retry limits
- **Error message quality**:
  - Actionable error messages
  - Not exposing internal details (stack traces)

**Tools**: `grep "try:"`, `grep "except:"`, `grep "HTTPException"`

**Output**: Error handling grade, missing try-except areas, recommendations

---

### 5. Code Smells & Anti-Patterns
Search for:
- **Giant files**: >1,000 lines
  - `app/routes/fo.py` (2,146 lines) - CRITICAL
  - `app/database.py` (1,914 lines)
- **Long functions**: >50 lines
  - Use `grep -A50 "def "` and count
- **God objects**: Classes with >20 methods
- **Magic numbers**: Hardcoded values (`30`, `0.25`, `"1 minute"`)
  - Should be in Settings class
- **Dead code**: Commented-out code, unused imports
- **Feature envy**: Accessing another object's data excessively

**Tools**: `wc -l **/*.py`, `grep "# "` (commented code), `grep "import"`

**Output**: Top 10 code smells, refactoring priorities

---

### 6. Testing & Testability
- **Existing test coverage**:
  - Find test files: `glob tests/**/*.py`, `glob *_test.py`, `glob test_*.py`
  - Count tests: `grep "def test_"`
  - Estimate coverage: tests / LOC
- **Code testability**:
  - Dependency injection used?
  - Global state prevents testing?
  - Mock-friendly design?
- **Edge case handling**:
  - Empty lists, None values, negative numbers
  - Boundary conditions

**Output**: Test coverage %, testability grade, missing tests

---

### 7. Configuration & Constants
- **Magic numbers**:
  - `30` seconds, `0.25` ratio, `100` items - what do they mean?
  - Should be: `CACHE_TTL_SECONDS = 30`
- **Hardcoded values**:
  - URLs, file paths, environment-specific logic
- **Configuration management**:
  - All config in Settings class?
  - Environment variable validation?

**Tools**: `grep "[0-9][0-9]"` (find numbers in code)

**Output**: Magic numbers list, recommendations for Settings class

---

### 8. API Contract Consistency
- **Endpoint naming**:
  - Consistent casing (kebab-case, snake_case, camelCase)
  - Plural vs singular (`/strategies` vs `/strategy`)
- **Response format**:
  - Consistent JSON structure
  - Pagination format uniform?
- **Error responses**:
  - Consistent error JSON format across endpoints
- **HTTP status codes**:
  - 200 vs 201 vs 204 (correct usage?)
  - 400 vs 422 (validation errors)

**Tools**: `read app/routes/*.py`, search for `@router.get`, `@router.post`

**Output**: API consistency grade, recommendations

---

### 9. Logging & Debugging
- **Log level appropriateness**:
  - DEBUG for verbose, INFO for normal, WARNING for issues, ERROR for failures
  - `logger.debug()` vs `logger.info()` usage
- **Log message quality**:
  - Actionable messages
  - Correlation IDs present
- **PII in logs**:
  - Passwords, API keys, user emails logged?
- **Debug aids**:
  - `print()` statements left in code (should use logger)

**Tools**: `grep "logger."`, `grep "print("`, `read app/main.py`

**Output**: Logging quality grade, PII exposure risks

---

### 10. Database Interactions
- **Query efficiency**:
  - Unnecessary `SELECT *`
  - Missing `LIMIT` clauses
  - Redundant queries (cache opportunities)
- **Connection management**:
  - Proper `async with pool.acquire()` usage
  - Connection leaks (missing `finally` blocks)
- **Transaction handling**:
  - Atomicity (all-or-nothing operations)
  - Rollback on errors

**Tools**: `grep "SELECT \*"`, `grep "pool.acquire"`, `read app/database.py`

**Output**: Database interaction quality, query optimization recommendations

---

## Deliverable Requirements

Create `/docs/assessment_1/phase3_code_expert_review.md` with:

### 1. Executive Summary
- Overall code quality grade (A-F)
- Top 10 most impactful improvements
- Critical refactoring priorities
- Estimated refactoring effort (weeks)

### 2. Code Quality Metrics
- Total lines of code: ~24,000
- Average function length: X lines
- Type hint coverage: X%
- Docstring coverage: X%
- Test coverage: X%
- Files >1,000 lines: Count
- Functions >50 lines: Count
- Cyclomatic complexity (estimate)

### 3. Detailed Findings
For each of 10 areas:
- Current state with examples
- Severity (Critical/High/Medium/Low)
- Affected files and line numbers
- Before/after code examples
- Effort estimate
- Impact on maintainability/performance/readability

### 4. Top 10 Code Quality Issues
Prioritized list with:
1. Issue description
2. Current code example
3. Recommended refactoring
4. Effort (hours)
5. Impact (High/Medium/Low)

### 5. Refactoring Roadmap
- Week 1: Critical issues (hardcoded secrets, giant files)
- Week 2-3: High-priority (type hints, error handling)
- Week 4-8: Medium-priority (docstrings, magic numbers)

---

## Example Output Snippet

### HIGH: Giant 2,146-Line Route File (fo.py)

**File**: `app/routes/fo.py`
**Lines**: 2,146 lines (CRITICAL - should be <500 lines per file)

**Current State**:
- 21 route handlers in one file
- Inline business logic (100+ line functions)
- WebSocket + REST mixed together
- Difficult to review, test, maintain

**Impact**:
- Code review time: 4-6 hours per PR
- Merge conflicts: 60% of PRs
- Onboarding difficulty: 2-3 weeks for new engineers
- Testing: Impossible to unit test routes

**Recommendation**: Split into 4 modules

```
app/routes/fo/
├── __init__.py
├── rest.py          # REST endpoints (500 lines)
├── websocket.py     # WebSocket endpoints (400 lines)
├── helpers.py       # Utility functions (300 lines)
└── services.py      # Business logic (600 lines)
```

**Refactoring Steps**:
1. Create `app/routes/fo/` directory
2. Move REST routes to `rest.py`
3. Move WebSocket routes to `websocket.py`
4. Extract business logic to `services.py`
5. Extract utilities to `helpers.py`
6. Update imports in `app/main.py`

**Effort**: 8-12 hours (includes testing, validation)
**Priority**: HIGH
**Impact**: Maintainability +50%, Code review time -70%
**Zero Regression**: ✅ API endpoints unchanged

---

## Final Checklist

- [ ] All 10 assessment areas completed
- [ ] Report saved to correct path
- [ ] Top 10 issues identified and prioritized
- [ ] Code examples (before/after) provided
- [ ] Metrics calculated (LOC, type hints %, etc.)
- [ ] Refactoring roadmap created
- [ ] Effort estimates realistic
- [ ] Zero regression guarantee

---

**Execution Command**:
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend
# Your code quality review begins here
```

**Expected Output**:
- **Report**: `/docs/assessment_1/phase3_code_expert_review.md`
- **Size**: 40-60 KB
- **Duration**: 4-6 hours
- **Next Step**: Phase 4 (QA Validation)

---

**END OF PROMPT**
