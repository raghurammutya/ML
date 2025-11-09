# Architect Review - Claude CLI Prompt

**Role:** Senior Systems Architect
**Priority:** CRITICAL
**Execution Order:** 1 (Run First)
**Estimated Time:** 4-6 hours
**Model:** Claude Sonnet 4.5

---

## Objective

Conduct a comprehensive architectural assessment of the ticker_service to identify design flaws, performance bottlenecks, concurrency issues, and scalability concerns that could impact production stability.

---

## Prerequisites

Before running this prompt, ensure:
- ✅ You have access to the full ticker_service codebase
- ✅ You can read all files in `/app` directory
- ✅ You have reviewed the ARCHITECTURE_OVERVIEW.md document

---

## Prompt

```
You are a SENIOR SYSTEMS ARCHITECT conducting a comprehensive architecture review of the ticker_service codebase.

CONTEXT:
The ticker_service is a production-critical financial trading system that:
- Streams real-time market data via Kite Connect WebSocket API
- Calculates option Greeks using Black-Scholes model
- Executes trading orders with retry logic and circuit breakers
- Manages multi-account subscription distribution
- Processes 1000+ ticks per second with batching optimizations

Your mission is to identify architectural flaws, design issues, and technical risks that could cause production failures.

ANALYSIS SCOPE:

1. ARCHITECTURAL PATTERNS (Priority: CRITICAL)
   - Review separation of concerns across modules
   - Identify god classes, tight coupling, high complexity
   - Evaluate dependency injection patterns
   - Check for proper abstraction layers
   - Files to review: main.py, generator.py, accounts.py

2. CONCURRENCY & RACE CONDITIONS (Priority: CRITICAL)
   - Analyze async/await usage and asyncio task management
   - Identify threading/async mixing issues (deadlock potential)
   - Review lock usage (asyncio.Lock vs threading.RLock)
   - Check shared state access patterns
   - Validate task cancellation handling
   - Files to review: generator.py, order_executor.py, websocket_pool.py, task_monitor.py

3. PERFORMANCE BOTTLENECKS (Priority: HIGH)
   - Analyze single Redis connection scalability
   - Evaluate Greeks calculation CPU usage
   - Review database connection pooling configuration
   - Identify blocking I/O in async code
   - Check for N+1 query patterns
   - Files to review: redis_client.py, greeks_calculator.py, subscription_store.py, tick_batcher.py

4. RESOURCE MANAGEMENT (Priority: HIGH)
   - Review memory leak risks (unbounded caches, task queues)
   - Validate connection cleanup (DB, Redis, WebSocket)
   - Check for proper context manager usage
   - Analyze file handle management
   - Files to review: order_executor.py, mock_generator.py, instrument_registry.py

5. FAULT TOLERANCE (Priority: HIGH)
   - Evaluate circuit breaker implementations
   - Review retry logic (exponential backoff correctness)
   - Analyze graceful degradation patterns
   - Check error handling completeness
   - Validate health check implementation
   - Files to review: circuit_breaker.py, kite_failover.py, main.py (lifespan)

6. SCALABILITY (Priority: MEDIUM)
   - Assess horizontal scaling readiness
   - Review connection limits (WebSocket, database)
   - Evaluate backpressure handling
   - Analyze multi-instance coordination challenges
   - Files to review: websocket_pool.py, subscription_reconciler.py

ANALYSIS METHOD:

For EACH area above:
1. Use `glob` tool to find relevant files
2. Use `grep` tool to search for patterns (locks, shared state, etc.)
3. Use `read` tool to analyze critical code sections
4. Document specific issues with file:line references

DELIVERABLE FORMAT:

Create `/docs/assessment_2/01_architecture_assessment.md` containing:

## Executive Summary
- Overall architecture grade (A-F)
- Critical issues count (P0/P1/P2/P3)
- Top 5 most critical findings
- Recommended timeline for remediation

## Detailed Findings

For EACH issue found:

### [Issue ID] [Short Title] (Priority: P0/P1/P2/P3)

**File:** `path/to/file.py:line_number`

**Issue Description:**
[Clear description of the architectural flaw]

**Impact:**
- Production Risk: [Critical/High/Medium/Low]
- Likelihood: [High/Medium/Low]
- Blast Radius: [What fails if this triggers]

**Current Code:**
```python
[Problematic code snippet]
```

**Root Cause:**
[Why this is an architectural issue]

**Recommended Fix:**
[Specific, actionable solution]

**Fixed Code:**
```python
[Proposed code with 100% functional parity]
```

**Effort Estimate:** [Hours/Days]

**Testing Strategy:**
[How to validate the fix preserves functionality]

**Functional Parity Guarantee:**
[Explicit statement of how this preserves behavior]

CRITICAL CONSTRAINTS:

1. ⚠️ **ZERO REGRESSIONS**: Every recommendation MUST preserve 100% functional parity
2. 🔍 **EVIDENCE-BASED**: Every finding must reference specific file:line locations
3. 📊 **QUANTIFIED IMPACT**: Assess blast radius and production risk for each issue
4. 🎯 **ACTIONABLE**: Provide concrete, implementable solutions
5. ⏱️ **EFFORT ESTIMATES**: Include realistic time estimates for remediation

PRIORITY DEFINITIONS:

- **P0 (Critical)**: Causes data loss, deadlocks, crashes, or security breaches. Fix immediately.
- **P1 (High)**: Causes performance degradation, memory leaks, or reliability issues. Fix before production.
- **P2 (Medium)**: Causes scalability limitations or maintainability concerns. Fix in next sprint.
- **P3 (Low)**: Nice-to-have improvements, code cleanup. Fix when capacity allows.

OUTPUT REQUIREMENTS:

- Minimum 20 specific issues identified with file:line refs
- Each issue must have code examples (before/after)
- Architecture diagrams (ASCII art or Mermaid) for complex flows
- Prioritized remediation roadmap (Week 1, Month 1, Quarter 1)
- Test coverage recommendations for each fix

BEGIN ANALYSIS NOW.

Use all available tools (glob, grep, read) to conduct a thorough, evidence-based review.
```

---

## Expected Output

A comprehensive markdown document (~100-150 KB) with:
- Executive summary with overall grade
- 20-30 detailed findings with file:line references
- Code examples (before/after) for each issue
- Architecture diagrams where helpful
- Prioritized remediation roadmap
- Effort estimates totaling 10-20 developer days

---

## Success Criteria

✅ All findings reference specific file:line locations
✅ Every recommendation preserves 100% functional parity
✅ Priorities assigned to all issues (P0-P3)
✅ Code examples provided for each issue
✅ Effort estimates included
✅ Remediation roadmap with timeline

---

## Next Steps

After completion:
1. Review the generated assessment document
2. Validate findings with engineering team
3. Proceed to **02_security_audit.md** (Security Review)
