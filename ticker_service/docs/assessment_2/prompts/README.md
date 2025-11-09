# Multi-Role Expert Assessment Prompts for Claude CLI

This directory contains **5 specialized Claude CLI prompts** designed to conduct a comprehensive, multi-role expert review of the `ticker_service` codebase.

---

## 📋 Overview

These prompts enable you to conduct a thorough production readiness assessment by simulating a team of 5 senior experts:

1. **Senior Systems Architect** - Architecture & Design Review
2. **Senior Security Engineer** - Security Audit & Compliance
3. **Senior Python/FastAPI Expert** - Code Quality Review
4. **Senior QA Manager** - Testing Validation & Coverage
5. **Senior Release Manager** - Production Deployment Decision

Each prompt is designed to be **executed sequentially** using Claude CLI, with each role building upon the findings of previous roles.

---

## 🎯 Execution Workflow

### **Recommended Execution Order**

```
01_architect_review.md
        ↓
02_security_audit.md
        ↓
03_code_expert_review.md
        ↓
04_qa_validation.md
        ↓
05_release_decision.md
```

**Why Sequential?**
- Each role provides context for the next
- Later roles reference findings from earlier assessments
- Final release decision synthesizes all findings

---

## 🚀 Quick Start

### Prerequisites

1. **Claude CLI Installed**: Ensure you have Claude Code CLI set up
2. **Repository Access**: Full access to the ticker_service codebase
3. **Permissions**: Ability to run pytest commands via bash
4. **Time Commitment**: 24-32 hours total (across all 5 prompts)

### Execution Steps

#### **Phase 1: Architecture Review** (4-6 hours)

```bash
# Navigate to the ticker_service directory
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service

# Copy the prompt content from 01_architect_review.md
# Paste into Claude CLI and execute
```

**Expected Output**: `./docs/assessment_2/01_architecture_assessment.md` (~100-150 KB)

---

#### **Phase 2: Security Audit** (6-8 hours)

**Prerequisites**: Phase 1 completed

```bash
# Ensure Phase 1 document exists
ls ./docs/assessment_2/01_architecture_assessment.md

# Copy prompt from 02_security_audit.md
# Paste into Claude CLI and execute
```

**Expected Output**: `./docs/assessment_2/02_security_audit.md` (~120-180 KB)

---

#### **Phase 3: Code Expert Review** (5-7 hours)

**Prerequisites**: Phases 1-2 completed

```bash
# Verify previous assessments exist
ls ./docs/assessment_2/01_architecture_assessment.md
ls ./docs/assessment_2/02_security_audit.md

# Copy prompt from 03_code_expert_review.md
# Paste into Claude CLI and execute
```

**Expected Output**: `./docs/assessment_2/03_code_expert_review.md` (~120-160 KB)

---

#### **Phase 4: QA Validation** (6-8 hours)

**Prerequisites**: Phases 1-3 completed

**Important**: This phase **executes actual tests** via pytest.

```bash
# Ensure test environment is ready
pip install -r requirements.txt

# Verify previous assessments exist
ls ./docs/assessment_2/0{1,2,3}_*.md

# Copy prompt from 04_qa_validation.md
# Paste into Claude CLI and execute
```

**Expected Output**: `./docs/assessment_2/04_qa_validation_report.md` (~150-200 KB)

**Note**: This phase will:
- Run `pytest --cov=app --cov-report=term-missing`
- Execute unit, integration, and load tests
- Generate coverage reports
- Document actual pass/fail results

---

#### **Phase 5: Production Release Decision** (3-4 hours)

**Prerequisites**: All phases 1-4 completed

**Critical**: This is the **final gate** before production deployment.

```bash
# Verify ALL previous assessments exist
ls ./docs/assessment_2/0{1,2,3,4}_*.md | wc -l  # Should show 4 files

# Copy prompt from 05_release_decision.md
# Paste into Claude CLI and execute
```

**Expected Output**: `./docs/assessment_2/05_production_release_decision.md` (~150-200 KB)

**Decision Outcomes**:
- ✅ **APPROVE**: Deploy to production with standard monitoring
- ⚠️ **APPROVE WITH CONDITIONS**: Deploy after specific fixes + validation
- ❌ **REJECT**: Block production until all critical issues resolved

---

## 📊 Expected Deliverables

### Assessment Reports Generated

| # | File | Size | Role | Execution Time |
|---|------|------|------|----------------|
| 1 | `01_architecture_assessment.md` | ~120 KB | Systems Architect | 4-6 hours |
| 2 | `02_security_audit.md` | ~150 KB | Security Engineer | 6-8 hours |
| 3 | `03_code_expert_review.md` | ~140 KB | Python/FastAPI Expert | 5-7 hours |
| 4 | `04_qa_validation_report.md` | ~180 KB | QA Manager | 6-8 hours |
| 5 | `05_production_release_decision.md` | ~170 KB | Release Manager | 3-4 hours |

**Total**: ~760 KB of comprehensive assessment documentation

---

## 🔍 What Each Assessment Covers

### 1️⃣ Architecture Assessment

**Focus**: Design flaws, concurrency issues, performance bottlenecks

**Analyzes**:
- Architectural patterns & separation of concerns
- Concurrency & race conditions (locks, async/await)
- Performance bottlenecks (Redis, Greeks CPU, DB pooling)
- Resource management (memory leaks, connection cleanup)
- Fault tolerance (circuit breakers, retry logic)
- Scalability (horizontal scaling readiness)

**Deliverables**:
- 20-30 specific issues with file:line references
- Architecture diagrams
- Prioritized remediation roadmap (P0-P3)
- Effort estimates for all fixes

---

### 2️⃣ Security Audit

**Focus**: Vulnerabilities, credential management, compliance

**Analyzes**:
- Authentication & authorization (JWT, API keys)
- Credential management (encryption, storage)
- Input validation (SQL injection, XSS, path traversal)
- Data protection (PII sanitization, HTTPS, CORS)
- Access control (Docker privileges, file permissions)
- Dependency security (CVEs, outdated packages)
- Compliance (PCI-DSS, SOC 2)

**Deliverables**:
- 15-25 vulnerabilities with CWE/CVE mapping
- CVSS scores and exploit scenarios
- OWASP Top 10 2021 coverage analysis
- PCI-DSS and SOC 2 compliance assessment
- Prioritized remediation roadmap

---

### 3️⃣ Code Expert Review

**Focus**: Code quality, maintainability, technical debt

**Analyzes**:
- Code quality metrics (complexity, duplication)
- Python best practices (type hints, async/await)
- FastAPI patterns (DI, routing, middleware)
- Testing & testability (coverage, test quality)
- Performance optimization opportunities
- Error handling & logging
- Resource management
- API design (RESTful conventions)

**Deliverables**:
- 25-35 code quality issues
- Code quality metrics (LOC, complexity, coverage)
- Technical debt inventory
- 5-10 quick wins (low effort, high impact)
- Prioritized roadmap

---

### 4️⃣ QA Validation

**Focus**: Test coverage, functional correctness, performance

**Analyzes**:
- Test coverage analysis (via pytest-cov)
- Functional correctness validation (actual test execution)
- Performance testing (tick throughput, API latency)
- Edge case & error handling
- Regression risk assessment
- Integration testing
- Data integrity validation
- Observability & monitoring

**Deliverables**:
- **Actual test execution results** (pass/fail counts)
- Real coverage percentages from pytest-cov
- Critical gap analysis with test recommendations
- Regression risk matrix
- Production readiness checklist
- Testing roadmap with effort estimates

---

### 5️⃣ Production Release Decision

**Focus**: Synthesize all findings, make deployment decision

**Analyzes**:
- All assessment reports (synthesizes findings)
- Production deployment risk
- Financial risk exposure
- Compliance requirements
- Operational readiness
- Rollback strategy

**Deliverables**:
- **Clear deployment decision** (APPROVE/REJECT/CONDITIONAL)
- Aggregated findings matrix (all P0/CRITICAL issues)
- Risk analysis with financial exposure
- Complete deployment plan with rollback procedure
- Monitoring strategy with alert thresholds
- Success criteria for post-deployment

---

## 🎯 Success Criteria

### For Each Assessment

✅ **Evidence-Based**: All findings reference specific `file:line` locations
✅ **Actionable**: Concrete fixes provided, not just identification
✅ **Quantified**: Effort estimates, risk levels, coverage percentages
✅ **Functional Parity**: All fixes preserve 100% behavioral compatibility
✅ **Comprehensive**: Minimum issue counts met per prompt

### For Overall Process

✅ **All 5 reports generated** in sequence
✅ **Consistent findings** across assessments (no contradictions)
✅ **Clear deployment decision** from Release Manager
✅ **Actionable roadmap** with timeline and effort estimates
✅ **Test validation** via actual pytest execution

---

## ⚠️ Critical Constraints

All prompts enforce these mandatory constraints:

1. **Zero Regressions**: Every recommendation MUST preserve 100% functional parity
2. **Evidence-Based**: Every finding must have file:line references
3. **Quantified Impact**: Assess risk, effort, and blast radius
4. **Actionable**: Provide concrete, implementable solutions
5. **Realistic Estimates**: Include honest time estimates for fixes

---

## 📈 Typical Findings Summary

Based on the completed assessments, expect to find:

### Architecture
- **5 P0 issues**: Deadlocks, memory leaks, single-point bottlenecks
- **8 P1 issues**: Performance degradation, concurrency flaws
- **12 P2 issues**: Scalability limitations, maintainability concerns
- **7 P3 issues**: Code cleanup, optimizations

### Security
- **4 CRITICAL**: Auth bypass, credential exposure, SSRF, injection
- **8 HIGH**: Missing encryption, weak validation, session fixation
- **7 MEDIUM**: Security hardening opportunities
- **4 LOW**: Minor improvements

### Code Quality
- **0 P0**: System is production-grade
- **5 P1**: God classes, high complexity, threading issues
- **8 P2**: Technical debt, refactoring opportunities
- **4 P3**: Documentation, dead code

### QA
- **Test Coverage**: 30-40% (vs. 70% target)
- **Critical Gaps**: Order execution, WebSocket auth, multi-account failover
- **Passing Tests**: 70-75% pass rate
- **Failing Tests**: 20-30 failures/errors needing fixes

### Release Decision
- **Typical Outcome**: **REJECT** or **APPROVE WITH CONDITIONS**
- **Blocking Issues**: 10-15 critical items
- **Remediation Timeline**: 4-6 weeks
- **Financial Risk**: $1M - $10M+ exposure if deployed prematurely

---

## 🔄 Iteration & Re-Assessment

After fixing identified issues:

1. **Re-run assessments** for affected areas
2. **Validate fixes** preserve functional parity
3. **Update coverage** metrics (should improve)
4. **Re-assess deployment decision** (should move toward APPROVE)

---

## 📞 Support & Questions

**Documentation**:
- Each prompt includes detailed instructions
- Expected outputs clearly defined
- Success criteria provided

**Common Issues**:
- **Prompt too long**: Split into multiple interactions if needed
- **Test execution fails**: Ensure dependencies installed (`pip install -r requirements.txt`)
- **Coverage reports missing**: Install pytest-cov (`pip install pytest-cov`)

---

## 🏆 Best Practices

1. **Execute in Order**: Don't skip phases - each builds on previous context
2. **Review Outputs**: Validate each assessment before proceeding to next
3. **Take Breaks**: 24-32 hours of assessment is intensive - spread over days
4. **Involve Team**: Share findings with engineering team for validation
5. **Track Progress**: Use generated reports to create Jira tickets
6. **Re-Assess**: After fixes, re-run affected assessments to validate

---

## 📅 Timeline Planning

### **Conservative Timeline** (Recommended)

- **Week 1**: Phase 1 (Architecture) + Phase 2 (Security)
- **Week 2**: Phase 3 (Code Quality) + Phase 4 (QA)
- **Week 3**: Phase 5 (Release Decision) + Team Review
- **Weeks 4-9**: Remediation of identified issues
- **Week 10**: Re-assessment + Production Deployment

### **Aggressive Timeline** (If Urgent)

- **Day 1-2**: Phases 1-2 (Architecture + Security)
- **Day 3-4**: Phases 3-4 (Code Quality + QA)
- **Day 5**: Phase 5 (Release Decision)
- **Weeks 2-7**: Remediation
- **Week 8**: Production Deployment

---

## 🎓 Learning from Assessments

These prompts are designed to:
- **Teach best practices** through detailed code examples
- **Build institutional knowledge** via comprehensive documentation
- **Improve code quality** through actionable recommendations
- **Reduce technical debt** with prioritized roadmaps
- **Enhance security posture** through vulnerability identification

---

## ✨ Final Notes

**This assessment framework is designed for production-critical financial systems.**

The prompts are conservative by design - they:
- Prioritize **safety over speed**
- Require **evidence over assumptions**
- Demand **functional parity** for all changes
- Quantify **financial risk exposure**
- Enforce **compliance requirements**

**Use these assessments to build confidence in production readiness, not to rush deployment.**

---

## 📝 Version History

- **v1.0** (2025-11-09): Initial release with 5 role-specific prompts
  - Architecture Assessment
  - Security Audit
  - Code Expert Review
  - QA Validation
  - Production Release Decision

---

## License

These prompts are part of the ticker_service internal documentation.

---

**Happy Assessing! 🚀**
