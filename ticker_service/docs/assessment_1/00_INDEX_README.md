# Assessment Action Items - Implementation Guide

**Generated:** 2025-11-09
**Source:** Multi-Phase Assessment (Phases 1-5)
**Status:** Ready for execution

---

## Overview

This directory contains **sequenced, role-specific prompts** for addressing all critical action items identified in the comprehensive 5-phase assessment of the ticker_service.

Each file is a **Claude CLI-ready prompt** that can be executed in order to systematically improve the codebase.

---

## Execution Priority & Sequence

### 🔴 P0 - CRITICAL (Must complete before production deployment)

**Security Fixes (BLOCKING):**
1. **[01_P0_SECURITY_SECRETS_REMEDIATION.md](./01_P0_SECURITY_SECRETS_REMEDIATION.md)**
   - **Role:** Security Engineer + DevOps
   - **Effort:** 4-6 hours
   - **Blocks:** Production deployment
   - **Actions:** Rotate DB password, revoke Kite token, implement KMS encryption, add CORS
   - **Dependencies:** None

**Test Coverage (Financial Risk):**
2. **[02_P0_ORDER_EXECUTOR_TESTING.md](./02_P0_ORDER_EXECUTOR_TESTING.md)**
   - **Role:** QA Engineer + Backend Engineer
   - **Effort:** 24 hours
   - **Target:** 90% coverage on order_executor.py
   - **Risk:** Financial losses from untested order placement
   - **Dependencies:** None

3. **[03_P0_WEBSOCKET_TESTING.md](./03_P0_WEBSOCKET_TESTING.md)**
   - **Role:** QA Engineer + Backend Engineer
   - **Effort:** 16 hours
   - **Target:** 85% coverage on routes_websocket.py
   - **Risk:** Client disconnections, data loss
   - **Dependencies:** None

4. **[04_P0_GREEKS_CALCULATION_TESTING.md](./04_P0_GREEKS_CALCULATION_TESTING.md)**
   - **Role:** Quant Engineer + QA Engineer
   - **Effort:** 20 hours
   - **Target:** 95% coverage on greeks_calculator.py
   - **Risk:** Mispriced options, trading losses
   - **Dependencies:** None

---

### 🟠 P1 - HIGH PRIORITY (Complete within 2 weeks)

**Architecture Improvements:**
5. **[05_P1_DEPENDENCY_INJECTION_REFACTOR.md](./05_P1_DEPENDENCY_INJECTION_REFACTOR.md)**
   - **Role:** Senior Backend Engineer
   - **Effort:** 16 hours
   - **Target:** Remove all 19 global singletons
   - **Benefits:** Testability, parallel test execution, no shared state
   - **Dependencies:** None (recommended before #6)

6. **[06_P1_GOD_CLASS_REFACTOR.md](./06_P1_GOD_CLASS_REFACTOR.md)**
   - **Role:** Senior Backend Engineer
   - **Effort:** 24 hours
   - **Target:** Split 757 LOC god class into 4 focused classes
   - **Benefits:** Maintainability, testability, reduced complexity
   - **Dependencies:** Recommended after #5

7. **07_P1_API_ENDPOINT_TESTING.md** (Create separately)
   - **Role:** QA Engineer
   - **Effort:** 32 hours
   - **Target:** 80% coverage on 50+ API endpoints
   - **Dependencies:** None

8. **08_P1_SECURITY_TEST_SUITE.md** (Create separately)
   - **Role:** Security Engineer + QA
   - **Effort:** 24 hours
   - **Target:** 100% coverage of OWASP Top 10 scenarios
   - **Dependencies:** #1 completed

---

### 🟡 P2 - MEDIUM PRIORITY (Complete within 1 month)

**Code Quality:**
9. **09_P2_EXCEPTION_HANDLING_REFACTOR.md** (Create separately)
   - **Role:** Backend Engineer
   - **Effort:** 6 hours
   - **Target:** Fix 69 bare exception catches
   - **Dependencies:** None

10. **10_P2_THREADING_RACE_CONDITIONS.md** (Create separately)
    - **Role:** Backend Engineer
    - **Effort:** 8 hours
    - **Target:** Replace daemon threads with ThreadPoolExecutor
    - **Dependencies:** None

11. **11_P2_DATABASE_INTEGRATION_TESTING.md** (Create separately)
    - **Role:** Backend Engineer + QA
    - **Effort:** 16 hours
    - **Target:** 80% coverage on database operations
    - **Dependencies:** None

12. **12_P2_MULTI_ACCOUNT_TESTING.md** (Create separately)
    - **Role:** QA Engineer
    - **Effort:** 12 hours
    - **Target:** Test round-robin, failover, concurrency
    - **Dependencies:** None

---

## Assessment Source Documents

The action items were derived from:

| Phase | Document | Focus Area | Key Findings |
|-------|----------|------------|--------------|
| 1 | [PHASE1_ARCHITECTURAL_REASSESSMENT.md](../PHASE1_ARCHITECTURAL_REASSESSMENT.md) | Architecture | 5 critical issues, 73/100 score |
| 2 | [PHASE2_SECURITY_AUDIT.md](../PHASE2_SECURITY_AUDIT.md) | Security | 4 CRITICAL blockers, 5.5/10 score |
| 3 | [PHASE3_CODE_REVIEW.md](../PHASE3_CODE_REVIEW.md) | Code Quality | 19 singletons, god class, 7.5/10 score |
| 4 | [PHASE4_QA_VALIDATION.md](../PHASE4_QA_VALIDATION.md) | Testing | 11% coverage, 4.2/10 score |
| 5 | [PHASE5_RELEASE_DECISION.md](../PHASE5_RELEASE_DECISION.md) | Deployment | Conditional approval |

---

## Recommended Execution Order

### Week 1: Security Hotfix (BLOCKING)
```bash
# Day 1-2: Security fixes (MANDATORY)
Execute: 01_P0_SECURITY_SECRETS_REMEDIATION.md

# Verify: All secrets removed, encryption working
pytest tests/security/ -v
```

### Week 2-3: Critical Test Coverage
```bash
# Week 2: Order + WebSocket testing
Execute: 02_P0_ORDER_EXECUTOR_TESTING.md
Execute: 03_P0_WEBSOCKET_TESTING.md

# Week 3: Greeks testing
Execute: 04_P0_GREEKS_CALCULATION_TESTING.md

# Verify: Coverage >= targets
pytest --cov=app --cov-report=html
```

### Week 4-5: Architecture Improvements
```bash
# Week 4: Dependency injection
Execute: 05_P1_DEPENDENCY_INJECTION_REFACTOR.md

# Week 5: God class refactor
Execute: 06_P1_GOD_CLASS_REFACTOR.md

# Verify: Tests pass, no shared state
pytest tests/ -n 8  # Parallel execution
```

### Week 6-8: Additional Testing & Hardening
```bash
# Week 6: API + Security tests
Execute: 07_P1_API_ENDPOINT_TESTING.md
Execute: 08_P1_SECURITY_TEST_SUITE.md

# Week 7-8: Code quality improvements
Execute: 09_P2_EXCEPTION_HANDLING_REFACTOR.md
Execute: 10_P2_THREADING_RACE_CONDITIONS.md

# Final verification
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Success Metrics

### After P0 Completion (Week 3):
- [ ] Security score: 5.5/10 → 8.0/10
- [ ] Test coverage: 11% → 50%
- [ ] Zero CRITICAL vulnerabilities
- [ ] Order/WebSocket/Greeks modules ≥ 85% coverage
- [ ] Production deployment approved

### After P1 Completion (Week 5):
- [ ] Code quality: 7.5/10 → 8.5/10
- [ ] Test coverage: 50% → 70%
- [ ] Zero global singletons
- [ ] God class eliminated
- [ ] Tests run in parallel

### After P2 Completion (Week 8):
- [ ] Test coverage: 70% → 85%
- [ ] Quality score: 8.5/10 → 9.2/10
- [ ] Technical debt < 10 hours
- [ ] All quality gates passed
- [ ] Full production approval

---

## How to Use These Prompts

### Option 1: Execute with Claude CLI

```bash
# Example: Security remediation
cat docs/assessment_1/01_P0_SECURITY_SECRETS_REMEDIATION.md | claude

# Follow the step-by-step instructions in the response
```

### Option 2: Execute as Standalone Tasks

1. Open prompt file
2. Copy entire content
3. Paste into Claude Code chat
4. Execute tasks sequentially as described
5. Verify acceptance criteria

### Option 3: Team Delegation

1. Assign each file to appropriate team member based on role
2. Team member reads prompt
3. Executes tasks with Claude assistance
4. Submits PR when acceptance criteria met
5. Lead reviews and approves

---

## Tracking Progress

Create a tracking spreadsheet:

| ID | Prompt File | Assignee | Status | Completion Date | PR Link |
|----|-------------|----------|--------|----------------|---------|
| 01 | Security Remediation | DevOps | ✅ Done | 2025-11-10 | #123 |
| 02 | Order Executor Tests | QA | 🟡 In Progress | - | - |
| 03 | WebSocket Tests | QA | ⚪ Not Started | - | - |
| ... | ... | ... | ... | ... | ... |

---

## Quality Gates

### Before Moving to Next Priority:

**P0 → P1:**
- [ ] All 4 P0 prompts completed
- [ ] Security vulnerabilities resolved
- [ ] Test coverage ≥ 50%
- [ ] Staging deployment successful

**P1 → P2:**
- [ ] All P1 prompts completed
- [ ] Architecture refactoring done
- [ ] Test coverage ≥ 70%
- [ ] No global singletons
- [ ] Tests run in parallel

**P2 → Production:**
- [ ] All P2 prompts completed
- [ ] Test coverage ≥ 85%
- [ ] Quality score ≥ 9.0/10
- [ ] All quality gates passed
- [ ] Final security review approved

---

## Support & Questions

**For prompt clarifications:**
- Review source assessment documents (../PHASE*.md)
- Consult with assessment team leads
- Reference original CVE/issue numbers

**For technical blockers:**
- Create GitHub issue with [ASSESSMENT] tag
- Link to specific prompt file
- Include error logs and context

**For priority questions:**
- Consult PHASE5_RELEASE_DECISION.md
- Escalate to Engineering Director
- Follow deployment authorization criteria

---

## Additional Resources

**Assessment Documents:**
- [PHASE1_ARCHITECTURAL_REASSESSMENT.md](../PHASE1_ARCHITECTURAL_REASSESSMENT.md) - Architecture quality
- [PHASE2_SECURITY_AUDIT.md](../PHASE2_SECURITY_AUDIT.md) - Security vulnerabilities
- [PHASE3_CODE_REVIEW.md](../PHASE3_CODE_REVIEW.md) - Code quality issues
- [PHASE4_QA_VALIDATION.md](../PHASE4_QA_VALIDATION.md) - Testing strategy
- [PHASE5_RELEASE_DECISION.md](../PHASE5_RELEASE_DECISION.md) - Deployment decision

**Test Plans:**
- [QA_ACTION_PLAN.md](../QA_ACTION_PLAN.md) - 8-week test improvement plan
- [QA_COMPREHENSIVE_ASSESSMENT.md](../QA_COMPREHENSIVE_ASSESSMENT.md) - Detailed test requirements
- [TEST_PLAN.md](../TEST_PLAN.md) - Original test strategy

**Implementation Guides:**
- [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) - Overall implementation strategy
- [REFACTORING_ROADMAP.md](../REFACTORING_ROADMAP.md) - Technical debt roadmap

---

## Version History

- **v1.0** (2025-11-09): Initial release
  - 6 detailed prompts (P0: 4, P1: 2)
  - Covers security, testing, architecture
  - Ready for team execution

---

## License & Usage

These prompts are internal documentation for the ticker_service improvement initiative. Use with Claude Code or Claude CLI for best results.

**Last Updated:** 2025-11-09
**Maintainer:** Engineering Leadership Team
**Review Cycle:** Weekly during execution phase
