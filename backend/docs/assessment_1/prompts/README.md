# Multi-Role Backend Assessment Prompts

This directory contains **5 comprehensive Claude CLI prompts** for conducting a thorough production-readiness assessment of the backend service. Each prompt represents a different expert role in the software development lifecycle.

---

## Execution Order

**IMPORTANT**: Execute these prompts in **sequential order**. Each phase builds on the findings of previous phases.

| Order | File | Role | Duration | Priority |
|-------|------|------|----------|----------|
| **1** | `01_architecture_review.md` | Senior Systems Architect | 4-6 hours | HIGH |
| **2** | `02_security_audit.md` | Senior Security Engineer | 6-8 hours | CRITICAL |
| **3** | `03_code_expert_review.md` | Senior Backend Engineer | 4-6 hours | HIGH |
| **4** | `04_qa_validation.md` | Senior QA Manager | 6-8 hours | CRITICAL |
| **5** | `05_release_decision.md` | Production Release Manager | 4-6 hours | CRITICAL |

**Total Estimated Time**: **24-34 hours** (3-4 working days)

---

## Quick Start

### Prerequisites

1. **Working Directory**: Ensure you are in `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend`
2. **Claude Code CLI**: Installed and configured
3. **Repository Access**: Read access to all backend files
4. **Output Directory**: `/docs/assessment_1/` exists (already created)

### Execution Method 1: Claude Code CLI

For each prompt (in order):

```bash
# Navigate to backend directory
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Execute Phase 1
claude code execute prompts/01_architecture_review.md

# Execute Phase 2 (after Phase 1 complete)
claude code execute prompts/02_security_audit.md

# Execute Phase 3 (after Phase 2 complete)
claude code execute prompts/03_code_expert_review.md

# Execute Phase 4 (after Phase 3 complete)
claude code execute prompts/04_qa_validation.md

# Execute Phase 5 (after Phase 4 complete - FINAL DECISION)
claude code execute prompts/05_release_decision.md
```

### Execution Method 2: Copy-Paste to Claude Code

1. Open Claude Code
2. Copy the entire content of `01_architecture_review.md`
3. Paste into Claude Code conversation
4. Wait for completion (4-6 hours)
5. Review output: `/docs/assessment_1/phase1_architecture_reassessment.md`
6. Repeat for phases 2-5

---

## Output Files

Each phase generates a comprehensive markdown report:

| Phase | Output File | Size | Purpose |
|-------|-------------|------|---------|
| 1 | `phase1_architecture_reassessment.md` | 50-100 KB | Architecture analysis, design patterns, scalability |
| 2 | `phase2_security_audit.md` | 50-100 KB | Security vulnerabilities, OWASP compliance, remediation |
| 3 | `phase3_code_expert_review.md` | 40-60 KB | Code quality, refactoring, best practices |
| 4 | `phase4_qa_validation.md` | 60-100 KB | Test coverage, quality metrics, test plan |
| 5 | `phase5_release_decision.md` | 50-80 KB | Production readiness verdict, timeline, go-live checklist |

**Total Documentation**: **250-440 KB** (100-150 pages)

---

## What Each Phase Delivers

### Phase 1: Architecture Reassessment
**Role**: Senior Systems Architect

**Deliverables**:
- Overall architecture grade (A-F)
- Codebase structure analysis
- Database architecture review (migrations, schema, indexes)
- API design consistency
- Scalability assessment (connection pooling, caching)
- Resilience & fault tolerance review
- Observability evaluation (logging, metrics, health checks)
- Top 10 architectural flaws with recommendations

**Key Questions Answered**:
- Can the system scale to 1,000+ concurrent users?
- Are there single points of failure?
- Is the database schema optimized?
- Is the caching strategy effective?

---

### Phase 2: Security Audit
**Role**: Senior Security Engineer

**Deliverables**:
- Security grade (A-F)
- CRITICAL vulnerabilities (CVSS 9.0+)
- HIGH vulnerabilities (CVSS 7.0-8.9)
- OWASP Top 10 compliance scorecard
- Authentication & authorization analysis
- Injection vulnerability assessment (SQL, NoSQL, command)
- Secrets management review
- Remediation roadmap with code examples

**Key Questions Answered**:
- Are there hardcoded secrets in git?
- Is WebSocket authentication implemented?
- Are API endpoints vulnerable to SQL injection?
- Is rate limiting configured?
- Can User A access User B's data?

---

### Phase 3: Code Expert Review
**Role**: Senior Backend Engineer

**Deliverables**:
- Code quality grade (A-F)
- Top 10 code improvements (prioritized)
- Code quality metrics (type hints %, docstring %, LOC)
- Design pattern analysis (SOLID, DRY)
- Performance bottlenecks (N+1 queries, algorithm efficiency)
- Error handling completeness
- Refactoring roadmap (week-by-week)

**Key Questions Answered**:
- Are files too large (>1,000 lines)?
- Is code properly typed and documented?
- Are there N+1 query patterns?
- Is error handling comprehensive?
- Are there code duplication opportunities?

---

### Phase 4: QA Validation
**Role**: Senior QA Manager

**Deliverables**:
- Quality grade (A-F)
- Current test coverage (%)
- Comprehensive test plan (847 tests total)
- Test case matrix (by feature, priority, effort)
- Critical testing gaps (top 10)
- Minimum test suite for production (120 tests)
- Production readiness verdict (APPROVED / CONDITIONAL / REJECTED)

**Key Questions Answered**:
- How much of the code is tested?
- Are financial calculations tested?
- Are integration tests present?
- Are security tests present?
- What's the minimum testing needed for production?

---

### Phase 5: Production Release Decision
**Role**: Production Release Manager

**Deliverables**:
- **FINAL DECISION**: APPROVED / CONDITIONAL APPROVAL / REJECTED
- Overall service grade (aggregate of Phases 1-4)
- Critical blockers count
- Production risk score (0-10)
- Timeline to production (2 weeks, 8-12 weeks)
- Go-Live checklist
- Rollback strategy
- Stakeholder communication templates

**Key Questions Answered**:
- Should we deploy to production?
- What are the critical blockers?
- How long until production ready?
- What's the deployment strategy?
- What are the rollback triggers?

---

## Assessment Framework

### Grading Scale

| Grade | Score | Interpretation | Production Readiness |
|-------|-------|----------------|----------------------|
| **A** | 90-100 | Excellent - Production ready | ✅ APPROVED |
| **B+** | 85-89 | Very Good - Minor improvements | ✅ CONDITIONAL |
| **B** | 80-84 | Good - Some improvements needed | ⚠️ CONDITIONAL |
| **B-** | 75-79 | Acceptable - Notable improvements needed | ⚠️ CONDITIONAL |
| **C+** | 70-74 | Below Average - Major improvements needed | ❌ REJECTED |
| **C** | 65-69 | Poor - Significant gaps | ❌ REJECTED |
| **D** | 60-64 | Very Poor - Critical issues | ❌ REJECTED |
| **F** | <60 | Failing - Not production ready | ❌ REJECTED |

### Severity Levels

**CRITICAL**: Blocking production deployment, immediate action required
**HIGH**: Must fix before full production, acceptable for soft launch with mitigations
**MEDIUM**: Should fix soon, not blocking
**LOW**: Nice to have, technical debt

### CVSS Scoring (Security)

| CVSS Score | Severity | Example |
|------------|----------|---------|
| **9.0-10.0** | CRITICAL | Hardcoded secrets in git, no authentication |
| **7.0-8.9** | HIGH | Missing rate limiting, weak CORS |
| **4.0-6.9** | MEDIUM | Missing security headers, weak passwords |
| **0.1-3.9** | LOW | Information disclosure, minor misconfigurations |

---

## Key Constraints

**All recommendations across all 5 phases MUST adhere to**:

1. **Zero Regression**: Preserve 100% functional parity
2. **No Breaking Changes**: Existing APIs remain backward-compatible
3. **Evidence-Based**: All findings cite specific files and line numbers
4. **Actionable**: Recommendations include concrete code examples
5. **Realistic**: Effort estimates account for testing and validation

---

## Common Issues Found (Historical Data)

Based on previous assessments, expect to find:

**Architecture**:
- ❌ Missing migration framework (Alembic)
- ❌ Connection pool too small (<20 connections)
- ❌ Global state anti-pattern
- ❌ Giant files (>1,000 lines)

**Security**:
- ❌ Hardcoded credentials in git (CRITICAL)
- ❌ Missing WebSocket authentication (CRITICAL)
- ❌ SQL injection via dynamic queries (CRITICAL)
- ❌ No rate limiting on trading endpoints (CRITICAL)
- ❌ Weak CORS configuration

**Code Quality**:
- ❌ Poor type hint coverage (<60%)
- ❌ Low docstring coverage (<40%)
- ❌ N+1 query patterns
- ❌ Magic numbers throughout code

**Testing**:
- ❌ Low test coverage (<5%)
- ❌ Zero tests for financial calculations
- ❌ Zero integration tests
- ❌ No CI/CD pipeline

---

## Success Metrics

### Phase 1 Success
- [x] Architecture grade assigned
- [x] Top 10 architectural flaws identified
- [x] Capacity analysis completed (connection pool, concurrent users)
- [x] Recommendations prioritized (Critical/High/Medium/Low)

### Phase 2 Success
- [x] Security grade assigned
- [x] All CRITICAL vulnerabilities (CVSS 9.0+) found
- [x] OWASP Top 10 compliance checked
- [x] Remediation roadmap created

### Phase 3 Success
- [x] Code quality grade assigned
- [x] Top 10 code improvements identified
- [x] Metrics calculated (type hints %, docstrings %, LOC)
- [x] Refactoring roadmap created

### Phase 4 Success
- [x] Quality grade assigned
- [x] Test coverage calculated (%)
- [x] 847-test comprehensive plan created
- [x] 120-test minimum plan for production created
- [x] Production readiness verdict assigned

### Phase 5 Success
- [x] Overall service grade calculated
- [x] Critical blockers counted
- [x] **FINAL DECISION**: APPROVED / CONDITIONAL / REJECTED
- [x] Timeline to production defined
- [x] Go-Live checklist created
- [x] Stakeholder communication templates provided

---

## Timeline Examples

### Fast Path (2 Weeks - Conditional Approval)
**Use Case**: Soft launch, demo accounts, 10% traffic

- **Week 1**: Fix 4 critical security vulnerabilities (6 days)
- **Week 2**: Implement 120 critical path tests (6 days)
- **Result**: 🟡 MEDIUM risk (acceptable for soft launch)
- **Cost**: ₹4-6 lakhs

### Recommended Path (8-12 Weeks - Full Production)
**Use Case**: Full production deployment, 100% traffic

- **Weeks 1-2**: Security fixes + migration framework (10 days)
- **Weeks 3-5**: 120 critical tests + CI/CD setup (15 days)
- **Weeks 6-10**: 847 comprehensive tests (25 days)
- **Weeks 11-12**: Integration & performance validation (10 days)
- **Result**: 🟢 LOW risk (full production confidence)
- **Cost**: ₹15-20 lakhs
- **ROI**: 10-15x in 6 months

---

## FAQ

### Q: Can I execute phases in parallel?
**A**: No. Each phase builds on previous findings. Execute sequentially.

### Q: What if I disagree with a finding?
**A**: Document your disagreement in the report, provide evidence, and escalate to team lead.

### Q: How long should each phase take?
**A**: 4-8 hours per phase. Do not rush - thoroughness is critical.

### Q: Can I skip phases?
**A**: No. All 5 phases are required for production deployment decision.

### Q: What if I find a CRITICAL issue mid-assessment?
**A**: Document it immediately, notify stakeholders, and continue assessment. The final decision (Phase 5) will consolidate all findings.

### Q: Can I modify the prompts?
**A**: Yes, but ensure you maintain the core assessment areas and deliverables.

---

## Support

If you encounter issues:

1. **Technical Issues**: Check Claude Code logs, verify file paths
2. **Ambiguities**: Document them in your report, analyze multiple scenarios
3. **Time Constraints**: Prioritize CRITICAL findings, defer MEDIUM/LOW to backlog
4. **Questions**: Contact assessment team lead

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-09 | Initial creation - All 5 prompts finalized |

---

**Last Updated**: 2025-11-09
**Maintained By**: Backend Assessment Team
**Next Review**: After first execution (feedback loop)

---

**Ready to begin? Start with Phase 1 (Architecture Review).**
