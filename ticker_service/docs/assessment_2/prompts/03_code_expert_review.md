# Code Expert Review - Claude CLI Prompt

**Role:** Senior Python/FastAPI Expert
**Priority:** HIGH
**Execution Order:** 3 (Run Third, After Security Audit)
**Estimated Time:** 5-7 hours
**Model:** Claude Sonnet 4.5

---

## Objective

Conduct a comprehensive code quality review of the ticker_service to identify code smells, anti-patterns, maintainability issues, performance optimizations, and technical debt that could impact long-term system health.

---

## Prerequisites

Before running this prompt, ensure:
- ✅ Architecture assessment completed (provides design context)
- ✅ Security audit completed (identifies security code issues)
- ✅ You have access to the full ticker_service codebase
- ✅ You can analyze test files in `/tests` directory

---

## Prompt

```
You are a SENIOR PYTHON/FASTAPI EXPERT conducting a comprehensive code quality review of the ticker_service.

CONTEXT:
The ticker_service is a production financial trading system built with:
- **Framework**: FastAPI (async-first web framework)
- **Language**: Python 3.11+
- **Patterns**: Async/await, dependency injection, repository pattern
- **Architecture**: Microservice with WebSocket streaming, background tasks
- **Scale**: Processes 1000+ ticks/second, manages multi-account subscriptions

Your mission is to identify code quality issues that impact:
- Maintainability (complexity, duplication, readability)
- Performance (inefficiencies, blocking I/O, N+1 queries)
- Testability (hard-to-test code, missing test coverage)
- Reliability (error handling, resource management)
- Developer productivity (technical debt, documentation gaps)

REVIEW SCOPE:

1. CODE QUALITY & MAINTAINABILITY (Priority: HIGH)
   - Cyclomatic complexity (functions >10 branches)
   - Cognitive complexity (nested if/for/while)
   - Function/class size (>100 LOC)
   - Code duplication (DRY violations)
   - Naming conventions (PEP 8 compliance)
   - Documentation quality (docstrings, comments)

   Files to review:
   - All files in /app directory
   - Focus on large files (>500 LOC)

   SPECIFIC CHECKS:
   - Use `grep -r "def " app/ | wc -l` to count functions
   - Search for god classes: `wc -l app/*.py | sort -n | tail -10`
   - Look for long functions: analyze main.py, generator.py, order_executor.py
   - Identify duplicated logic across modules

2. PYTHON BEST PRACTICES (Priority: HIGH)
   - Type hints coverage (functions, returns, variables)
   - Error handling patterns (specific exceptions vs. bare except)
   - Context managers (with statements for resources)
   - Async/await correctness (no blocking I/O)
   - Generator/iterator usage
   - Dataclasses vs. dicts

   Files to review:
   - All .py files in /app

   SPECIFIC CHECKS:
   - Search for missing type hints: `grep -r "def.*->" app/ -c`
   - Find bare except: `grep -r "except:" app/`
   - Check for blocking I/O in async: `grep -r "time.sleep\|requests\." app/`
   - Verify proper exception handling

3. FASTAPI PATTERNS (Priority: HIGH)
   - Dependency injection usage (Depends())
   - Router organization (logical grouping)
   - Response models (Pydantic schemas)
   - Exception handlers (global vs. local)
   - Middleware implementation
   - Lifespan management

   Files to review:
   - main.py (app setup, middleware)
   - routes_*.py (all route files)
   - dependencies.py
   - api_models.py

   SPECIFIC CHECKS:
   - Verify all endpoints have response_model
   - Check for missing dependencies (database, auth)
   - Validate exception handling consistency
   - Review middleware order and configuration

4. TESTING & TESTABILITY (Priority: HIGH)
   - Unit test coverage gaps
   - Integration test coverage
   - Test quality (assertions, edge cases)
   - Mocking strategies (proper isolation)
   - Test data management
   - Fixture organization

   Files to review:
   - /tests directory (all test files)
   - conftest.py (shared fixtures)

   SPECIFIC CHECKS:
   - Run: `pytest --cov=app --cov-report=term-missing` (if possible)
   - Count test files: `find tests/ -name "test_*.py" | wc -l`
   - Look for missing tests for critical modules
   - Check test naming conventions

5. PERFORMANCE OPTIMIZATION (Priority: MEDIUM)
   - N+1 query patterns
   - Inefficient loops (quadratic complexity)
   - Unnecessary data copies
   - Blocking I/O in async code
   - Cache utilization opportunities
   - Database query optimization

   Files to review:
   - subscription_store.py (database queries)
   - greeks_calculator.py (computation-heavy)
   - tick_processor.py (hot path)
   - generator.py (streaming logic)

   SPECIFIC CHECKS:
   - Search for loops with database calls: patterns like `for ... await db.query`
   - Look for list comprehensions that could be generators
   - Identify repeated calculations (cache candidates)
   - Find synchronous HTTP calls in async functions

6. ERROR HANDLING & LOGGING (Priority: MEDIUM)
   - Exception hierarchy (custom exceptions)
   - Error propagation (proper re-raising)
   - Logging levels (DEBUG/INFO/WARNING/ERROR)
   - Contextual logging (structured logging)
   - Observability hooks (metrics, tracing)

   Files to review:
   - All .py files for exception handling
   - main.py (logging configuration)

   SPECIFIC CHECKS:
   - Search for bare except: `grep -r "except:" app/`
   - Check logging usage: `grep -r "logger\." app/ | wc -l`
   - Verify exception messages are descriptive
   - Look for missing try/except in critical paths

7. RESOURCE MANAGEMENT (Priority: MEDIUM)
   - Connection cleanup (context managers)
   - Task cancellation handling
   - Memory leak risks (unbounded caches)
   - File handle management
   - Thread pool cleanup

   Files to review:
   - redis_client.py
   - subscription_store.py
   - order_executor.py
   - generator.py

   SPECIFIC CHECKS:
   - Verify all connections use context managers
   - Check for proper async cleanup in finally blocks
   - Look for unbounded data structures (lists, dicts)
   - Validate task cancellation handling

8. API DESIGN (Priority: LOW)
   - RESTful conventions (HTTP methods, status codes)
   - Versioning strategy
   - Pagination implementation
   - Rate limiting application
   - Request/response schemas

   Files to review:
   - All routes_*.py files
   - api_models.py

   SPECIFIC CHECKS:
   - Verify proper HTTP methods (GET/POST/PUT/DELETE)
   - Check for missing pagination on list endpoints
   - Validate rate limiting on expensive endpoints
   - Review API consistency (naming, structure)

ANALYSIS METHOD:

For EACH area:
1. Use `glob` to find relevant files
2. Use `grep` to search for patterns (anti-patterns, code smells)
3. Use `read` to analyze specific code sections
4. Use `bash` to run code metrics tools (if available)
5. Document issues with file:line references and code examples

CODE METRICS TO CALCULATE:

- **Lines of Code**: Total, per module, per function
- **Cyclomatic Complexity**: Functions with >10 branches
- **Type Hint Coverage**: % of functions with type hints
- **Test Coverage**: % of code covered by tests
- **Duplication**: Repeated code blocks (>5 lines)
- **Technical Debt**: Estimated time to fix all issues

DELIVERABLE FORMAT:

Create `/docs/assessment_2/03_code_expert_review.md` containing:

## Executive Summary
- Overall code quality grade (A-F)
- Critical issues count (P0/P1/P2/P3)
- Top 5 most impactful improvements
- Technical debt estimate (developer days)

## Code Quality Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total LOC | X,XXX | - | - |
| Type Hint Coverage | XX% | 90% | ✅/❌ |
| Test Coverage | XX% | 80% | ✅/❌ |
| Functions >100 LOC | XX | <5 | ✅/❌ |
| Cyclomatic Complexity >10 | XX | <10 | ✅/❌ |
| Code Duplication | XX% | <5% | ✅/❌ |

## Detailed Findings

For EACH issue:

### [Issue ID] [Short Title] (Priority: P0/P1/P2/P3)

**Category:** [Code Quality / Performance / Testability / Error Handling]
**File:** `path/to/file.py:line_number`

**Issue Description:**
[Clear description of the code quality issue]

**Impact:**
- Maintainability: [HIGH/MEDIUM/LOW]
- Performance: [HIGH/MEDIUM/LOW]
- Testability: [HIGH/MEDIUM/LOW]
- Developer Productivity: [HIGH/MEDIUM/LOW]

**Current Code:**
```python
[Problematic code snippet with line numbers]
```

**Code Smell:**
[What anti-pattern or smell this represents]

**Root Cause:**
[Why this code was written this way]

**Recommended Refactoring:**
[Specific, actionable improvement]

**Refactored Code:**
```python
[Improved code with best practices]
```

**Benefits:**
- [Specific improvements gained]
- [Metrics that improve (complexity, readability, etc.)]

**Effort Estimate:** [Hours/Days]

**Testing Strategy:**
[How to ensure refactoring preserves behavior]

**Functional Parity Guarantee:**
[Explicit statement of behavior preservation]

## Technical Debt Inventory

| ID | Component | Issue | Priority | Effort | Impact |
|----|-----------|-------|----------|--------|--------|
| TD-001 | generator.py | God class (766 LOC) | P1 | 2 days | High |
| TD-002 | main.py | Lifespan complexity | P2 | 1 day | Medium |

## Quick Wins

Low-effort, high-impact improvements:

### QW-1: [Quick Win Title]
- **Effort**: X hours
- **Impact**: [Specific benefit]
- **File**: file.py:line
- **Change**: [One-line description]

## Actionable Roadmap

**Week 1 (Quick Wins):**
- [List all quick wins]
- Total effort: X hours

**Month 1 (High Priority):**
- [List all P1 issues]
- Total effort: Y days

**Quarter 1 (Medium Priority):**
- [List all P2 issues]
- Total effort: Z days

**Ongoing (Low Priority):**
- [List all P3 issues]

CRITICAL CONSTRAINTS:

1. ⚠️ **ZERO BEHAVIORAL CHANGES**: All refactoring MUST preserve 100% functionality
2. 🔍 **EVIDENCE-BASED**: Every finding must have file:line reference and code example
3. 📊 **METRICS-DRIVEN**: Quantify complexity, duplication, coverage
4. 🎯 **ACTIONABLE**: Provide concrete, implementable solutions
5. ⏱️ **EFFORT ESTIMATES**: Include realistic time estimates

PRIORITY DEFINITIONS:

- **P0 (Critical)**: Code that causes production issues or security vulnerabilities. Fix immediately.
- **P1 (High)**: Significant maintainability or performance issues. Fix before next release.
- **P2 (Medium)**: Technical debt that impacts developer productivity. Fix in next sprint.
- **P3 (Low)**: Nice-to-have improvements, code cleanup. Fix when capacity allows.

OUTPUT REQUIREMENTS:

- Minimum 25-35 code quality issues identified
- Code quality metrics calculated (LOC, complexity, coverage)
- Each issue must have code examples (before/after)
- Technical debt inventory with effort estimates
- 5-10 quick wins identified
- Prioritized roadmap with timeline

BEGIN REVIEW NOW.

Use all available tools (glob, grep, read, bash) to conduct a thorough, evidence-based code quality review.
```

---

## Expected Output

A comprehensive code quality review document (~120-160 KB) with:
- Executive summary with overall grade
- Code quality metrics table
- 25-35 detailed findings with file:line references
- Code examples (before/after) for each issue
- Technical debt inventory
- 5-10 quick wins
- Prioritized roadmap
- Total effort estimate (typically 10-25 developer days)

---

## Success Criteria

✅ All findings reference specific file:line locations
✅ Code quality metrics calculated and tabulated
✅ Every refactoring preserves 100% functional parity
✅ Code examples (before/after) for all issues
✅ Effort estimates included for all improvements
✅ Quick wins identified (low effort, high impact)
✅ Roadmap with timeline (Week 1, Month 1, Quarter 1)

---

## Next Steps

After completion:
1. Review findings with engineering team
2. Prioritize technical debt items based on impact/effort
3. Create Jira tickets for high-priority improvements
4. Proceed to **04_qa_validation.md** (QA Testing Review)
