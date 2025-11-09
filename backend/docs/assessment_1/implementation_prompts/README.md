# Backend Implementation Prompts

**Purpose**: Step-by-step implementation guides to address critical findings from the 5-phase production readiness assessment.

**Status**: Ready for execution
**Created**: 2025-11-09
**Last Updated**: 2025-11-09

---

## Overview

This directory contains **5 comprehensive implementation prompts** to fix critical issues identified in the backend assessment. These prompts are designed for **execution by engineers** (or Claude Code) to implement production-ready fixes.

**Assessment Results** (Reference: `/docs/assessment_1/`):
- Overall Grade: **C- (63/100)** - REJECTED for production
- Critical Blockers: **18 items**
- Production Risk: **8.5/10 (CRITICAL)**

---

## Execution Order

**IMPORTANT**: Execute prompts in **sequential order** based on priority.

| Order | Prompt | Priority | Duration | Blocking Production? |
|-------|--------|----------|----------|----------------------|
| **1** | `01_security_remediation.md` | **P0 - CRITICAL** | 6-8 days | ✅ YES |
| **2** | `02_critical_testing.md` | **P0 - CRITICAL** | 10-12 days | ✅ YES |
| **3** | `03_strategy_system_completion.md` | P1 - HIGH | 12-18 hours | ❌ NO (feature) |
| **4** | `04_architecture_fixes.md` | P1 - HIGH | 5-7 days | ⚠️ PARTIAL (scalability) |
| **5** | `05_code_quality_improvements.md` | P2 - MEDIUM | 3-4 weeks | ❌ NO (tech debt) |

---

## Prompt Summaries

### 1. Security Remediation (Week 1 - CRITICAL)

**File**: `01_security_remediation.md`
**Duration**: 6-8 days (1 engineer full-time)
**Priority**: P0 - BLOCKING PRODUCTION

**Objective**: Fix **4 CRITICAL security vulnerabilities** (CVSS 9.0+)

**Fixes**:
1. ✅ Remove hardcoded database credentials from git (CVSS 10.0)
2. ✅ Add WebSocket JWT authentication (CVSS 9.1)
3. ✅ Fix SQL injection vulnerabilities (CVSS 9.8)
4. ✅ Implement rate limiting on trading endpoints (CVSS 9.0)

**Success Criteria**:
- Security Grade: C+ (69/100) → B+ (85/100)
- CRITICAL vulnerabilities: 4 → 0
- OWASP Top 10 compliance: 40% → 80%

**Impact**: **CRITICAL** - Enables production deployment

---

### 2. Critical Testing (Weeks 2-3)

**File**: `02_critical_testing.md`
**Duration**: 10-12 days (1-2 engineers)
**Priority**: P0 - BLOCKING PRODUCTION

**Objective**: Implement **120 critical path tests** to validate financial calculations

**Test Suites**:
1. ✅ Strategy M2M Calculation (25 tests)
2. ✅ F&O Greeks Calculations (20 tests)
3. ✅ Decimal Precision (10 tests)
4. ✅ Database Operations (30 tests)
5. ✅ Authentication & Authorization (30 tests)
6. ✅ API Contract Testing (5 tests)

**Success Criteria**:
- Test coverage: 2.7% → 40%+
- Financial calculation tests: 0 → 55
- QA Grade: D+ (47/100) → B (80/100)

**Impact**: **CRITICAL** - Validates financial correctness

---

### 3. Strategy System Completion (Weeks 4-12)

**File**: `03_strategy_system_completion.md`
**Duration**: 12-18 hours (backend only)
**Priority**: P1 - Feature Completion

**Objective**: Complete Phase 2.5 Strategy System (currently 70% incomplete)

**Implementation**:
1. ✅ Database migrations (4 new tables)
2. ✅ Backend routes (10+ API endpoints)
3. ✅ M2M calculation worker
4. ⏳ Frontend components (7 components - separate effort)

**Success Criteria**:
- Phase 2.5 completion: 30% → 100% (backend)
- Strategy system: Fully functional
- Users can create strategies, track M2M, export P&L

**Impact**: HIGH - Unlocks strategy-based trading

---

### 4. Architecture Fixes (Week 4)

**File**: `04_architecture_fixes.md`
**Duration**: 5-7 days (1 engineer)
**Priority**: P1 - HIGH

**Objective**: Fix **3 critical architectural issues**

**Fixes**:
1. ✅ Implement Alembic migration framework (zero-downtime deployments)
2. ✅ Increase connection pool: 20 → 100 (scale to 100 concurrent users)
3. ✅ Eliminate global state (dependency injection pattern)

**Success Criteria**:
- Architecture Grade: B+ (82/100) → A (90/100)
- Migration framework: Missing → Alembic
- Connection pool: 20 → 100 (5x capacity)
- Global state: 15 variables → 0

**Impact**: CRITICAL - Enables production scalability

---

### 5. Code Quality Improvements (Weeks 5-8)

**File**: `05_code_quality_improvements.md`
**Duration**: 3-4 weeks (part-time, 1-2 engineers)
**Priority**: P2 - MEDIUM (Technical Debt)

**Objective**: Address **top 5 code quality issues**

**Improvements**:
1. ✅ Split giant files (fo.py: 2,146 lines → 4 modules <500 lines each)
2. ✅ Add type hints (58% → 95% coverage)
3. ✅ Add docstrings (40% → 95% coverage)
4. ✅ Fix N+1 query patterns (90% faster)
5. ✅ Eliminate magic numbers (centralize in Settings)

**Success Criteria**:
- Code Quality Grade: B- (72/100) → A (90/100)
- Type hints: 58% → 95%
- Docstrings: 40% → 95%
- File sizes: All <1,000 lines

**Impact**: HIGH - Improves maintainability by 50%

---

## Execution Paths

### Fast Path (2 Weeks - Conditional Approval)

**Use Case**: Soft launch, demo accounts, 10% traffic

**Execute**:
1. ✅ Prompt 01: Security Remediation (Week 1)
2. ✅ Prompt 02: Critical Testing (120 tests only) (Week 2)

**Result**:
- 🟡 MEDIUM risk (acceptable for soft launch)
- Cost: ₹4-6 lakhs (2 engineers × 2 weeks)
- Timeline: **2 weeks**

---

### Recommended Path (8-12 Weeks - Full Production)

**Use Case**: Full production deployment, 100% traffic

**Execute**:
1. ✅ Prompt 01: Security Remediation (Week 1)
2. ✅ Prompt 02: Critical Testing (Week 2-3)
3. ✅ Prompt 04: Architecture Fixes (Week 4)
4. ✅ Prompt 05: Code Quality (Weeks 5-8)
5. ⏳ Prompt 02: Expand testing (120 → 847 tests) (Weeks 9-12)

**Result**:
- 🟢 LOW risk (full production confidence)
- Cost: ₹15-20 lakhs (2-3 engineers × 8-12 weeks)
- ROI: 10-15x in 6 months (avoided incidents, user trust)
- Timeline: **8-12 weeks**

---

### Feature-Complete Path (16-20 Weeks)

**Use Case**: Full production + Phase 2.5 Strategy System

**Execute**: All 5 prompts in order

**Result**:
- 🟢 LOW risk + Full feature parity
- Cost: ₹20-25 lakhs
- Timeline: **16-20 weeks**

---

## How to Use These Prompts

### Method 1: Claude Code Execution

```bash
# Navigate to backend directory
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Execute Prompt 1 (Security)
claude code execute docs/assessment_1/implementation_prompts/01_security_remediation.md

# Execute Prompt 2 (Testing)
claude code execute docs/assessment_1/implementation_prompts/02_critical_testing.md

# Continue with remaining prompts in order...
```

### Method 2: Manual Implementation

1. Open prompt file (e.g., `01_security_remediation.md`)
2. Follow step-by-step instructions
3. Copy code examples and adapt to codebase
4. Run validation steps after each task
5. Check off items in final checklist

### Method 3: Team Distribution

**Week 1** (Security - 1 engineer):
- Engineer A: Execute Prompt 01 (6-8 days)

**Weeks 2-3** (Testing - 2 engineers):
- Engineer A: Financial calculation tests (Task 1-3)
- Engineer B: Database & security tests (Task 4-5)

**Week 4** (Architecture - 1 engineer):
- Engineer A: Execute Prompt 04 (5-7 days)

**Weeks 5-8** (Code Quality - 2 engineers part-time):
- Engineer A: File splitting, type hints
- Engineer B: Docstrings, N+1 fixes, constants

---

## Success Metrics

### Before Implementation

**From Assessment** (`/docs/assessment_1/phase5_release_decision.md`):
- Overall Grade: **C- (63/100)**
- Security: C+ (69/100) - 4 CRITICAL vulnerabilities
- Testing: D+ (47/100) - 2.7% coverage
- Architecture: B+ (82/100) - Missing migration framework
- Code Quality: B- (72/100) - Giant files, poor type hints
- **Production Risk**: 8.5/10 (CRITICAL)
- **Decision**: REJECTED

### After Fast Path (2 Weeks)

- Overall Grade: **B (75/100)**
- Security: B+ (85/100) - 0 CRITICAL vulnerabilities
- Testing: B (60/100) - 40% coverage
- **Production Risk**: 6.0/10 (MEDIUM)
- **Decision**: CONDITIONAL APPROVAL (soft launch)

### After Recommended Path (8-12 Weeks)

- Overall Grade: **A- (88/100)**
- Security: A (95/100)
- Testing: A- (87/100) - 90% coverage
- Architecture: A (90/100)
- Code Quality: A (90/100)
- **Production Risk**: 2.0/10 (LOW)
- **Decision**: APPROVED (full production)

---

## Validation Checklists

Each prompt includes:
- ✅ **Zero Regression Checklist**: Ensure existing functionality unchanged
- ✅ **Validation Steps**: Test after each task
- ✅ **Success Criteria**: Measurable goals
- ✅ **Final Checklist**: Confirm all tasks complete

---

## Files Created by Prompts

### Security Remediation (Prompt 01)
- `.env.template` - Environment variable template
- `app/dependencies.py` - WebSocket authentication
- `tests/security/test_sql_injection.py` - Security tests
- `tests/security/test_rate_limiting.py` - Rate limit tests

### Critical Testing (Prompt 02)
- `tests/unit/test_strategy_m2m.py` - M2M calculation tests (25 tests)
- `tests/unit/test_greeks_calculations.py` - Greeks tests (20 tests)
- `tests/unit/test_decimal_precision.py` - Decimal precision tests (10 tests)
- `tests/integration/test_database_pooling.py` - Database tests (30 tests)
- `tests/security/test_jwt_authentication.py` - Auth tests (30 tests)
- `.github/workflows/test.yml` - CI/CD pipeline

### Strategy System (Prompt 03)
- `migrations/025_create_strategies_table.sql`
- `migrations/026_create_strategy_instruments_table.sql`
- `migrations/027_create_strategy_m2m_candles_table.sql`
- `migrations/028_create_strategy_performance_daily_table.sql`
- `app/routes/strategies.py` - Strategy API endpoints
- `app/workers/strategy_m2m_worker.py` - M2M calculation worker

### Architecture Fixes (Prompt 04)
- `alembic/` - Migration framework
- `alembic.ini` - Alembic configuration
- `docs/MIGRATIONS.md` - Migration documentation
- `app/dependencies.py` - Dependency injection (updated)

### Code Quality (Prompt 05)
- `app/routes/fo/` - Split fo.py module
- `app/database/` - Split database.py module
- `mypy.ini` - Type checker configuration
- `.pydocstyle` - Docstring linter configuration

---

## Common Issues

### Issue 1: Import Errors After Refactoring

**Symptom**: `ModuleNotFoundError: No module named 'app.routes.fo'`
**Solution**: Update `__init__.py` files to re-export modules

### Issue 2: Database Migration Conflicts

**Symptom**: `alembic.util.exc.CommandError: Multiple head revisions`
**Solution**: Merge heads with `alembic merge heads`

### Issue 3: Test Failures After Changes

**Symptom**: Existing tests fail after implementation
**Solution**: Review zero regression checklist, update tests if API changed

---

## Support & Questions

**Questions?** Contact:
- **Backend Team Lead**: Review assessment findings in `/docs/assessment_1/`
- **Security Team**: Reference `phase2_security_audit.md`
- **QA Team**: Reference `phase4_qa_validation.md`

**Documentation**:
- Assessment Reports: `/docs/assessment_1/phase*.md`
- Master Index: `/docs/assessment_1/MASTER_INDEX.md`
- Quick Summaries: `/docs/assessment_1/SECURITY_SUMMARY.md`, `QA_SUMMARY.md`

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-09 | Initial creation - All 5 prompts finalized |

---

**Last Updated**: 2025-11-09
**Maintained By**: Backend Assessment Team
**Next Review**: After first implementation (feedback loop)

---

**Ready to begin? Start with Prompt 01 (Security Remediation).**
