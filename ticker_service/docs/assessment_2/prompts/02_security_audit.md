# Security Audit - Claude CLI Prompt

**Role:** Senior Security Engineer
**Priority:** CRITICAL
**Execution Order:** 2 (Run Second, After Architecture Review)
**Estimated Time:** 6-8 hours
**Model:** Claude Sonnet 4.5

---

## Objective

Conduct a comprehensive security audit of the ticker_service to identify vulnerabilities, credential management issues, authentication flaws, and compliance gaps that could expose the system to attacks or data breaches.

---

## Prerequisites

Before running this prompt, ensure:
- ✅ Architecture assessment completed (provides context on design issues)
- ✅ You have access to the full ticker_service codebase
- ✅ You can inspect configuration files (.env.example, requirements.txt)
- ✅ You understand this is a financial trading system handling sensitive data

---

## Prompt

```
You are a SENIOR SECURITY ENGINEER conducting a comprehensive security audit of the ticker_service.

CONTEXT:
The ticker_service is a production financial trading system that:
- Handles sensitive trading API credentials (Kite Connect)
- Processes financial transactions with real money at stake
- Stores customer trading account information
- Implements JWT authentication for user access
- Must comply with PCI-DSS and SOC 2 requirements

Your mission is to identify security vulnerabilities that could lead to:
- Credential theft or unauthorized API access
- Financial loss through unauthorized trades
- Data breaches exposing customer information
- Regulatory compliance violations
- Denial of service attacks

AUDIT SCOPE:

1. AUTHENTICATION & AUTHORIZATION (Priority: CRITICAL)
   - JWT token validation implementation
   - API key authentication mechanism
   - Token expiration and rotation
   - Service-to-service authentication
   - Authorization checks on endpoints
   - Session management security

   Files to review:
   - jwt_auth.py (JWT validation logic)
   - auth.py (API key authentication)
   - routes_*.py (endpoint authorization checks)
   - middleware.py (authentication middleware)

   SPECIFIC CHECKS:
   - Search for timing attack vulnerabilities in string comparison
   - Verify JWT signature validation (not just decode)
   - Check for JWKS URL validation (SSRF risk)
   - Validate token expiration enforcement
   - Look for missing authorization checks

2. CREDENTIAL MANAGEMENT (Priority: CRITICAL)
   - Encryption at rest for sensitive data
   - API key/secret storage security
   - Access token file permissions
   - Environment variable handling
   - Hardcoded secrets detection
   - Encryption key management

   Files to review:
   - crypto.py (encryption implementation)
   - account_store.py (credential storage)
   - config.py (secret handling)
   - kite/tokens/*.json (token file permissions)
   - .env.example (hardcoded secrets check)

   SPECIFIC CHECKS:
   - Search for hardcoded API keys/passwords: `grep -r "api_key\s*=\s*['\"]" app/`
   - Check for cleartext credential storage
   - Validate encryption key generation (random vs. fixed)
   - Verify file permissions on token files (should be 600)
   - Check for credentials in logs

3. INPUT VALIDATION & INJECTION RISKS (Priority: CRITICAL)
   - SQL injection vulnerabilities
   - Command injection risks
   - Path traversal vulnerabilities
   - XSS in error messages
   - Request validation completeness

   Files to review:
   - subscription_store.py (database queries)
   - account_store.py (database queries)
   - All routes_*.py files (input validation)
   - api_models.py (Pydantic schemas)

   SPECIFIC CHECKS:
   - Search for f-string SQL queries: `grep -r "f\".*SELECT\|INSERT\|UPDATE\|DELETE" app/`
   - Check for string concatenation in queries
   - Verify all parameters use Pydantic validation
   - Look for subprocess calls with user input
   - Check for file path validation

4. DATA PROTECTION (Priority: HIGH)
   - PII sanitization in logs
   - Sensitive data in API responses
   - HTTPS enforcement
   - CORS configuration security
   - Encryption in transit

   Files to review:
   - main.py (PII sanitization, CORS config)
   - routes_*.py (response data filtering)
   - config.py (HTTPS settings)

   SPECIFIC CHECKS:
   - Verify PII sanitization covers all patterns
   - Check CORS allows unsafe origins
   - Look for sensitive fields in responses (passwords, tokens)
   - Validate HTTPS enforcement in production

5. ACCESS CONTROL (Priority: HIGH)
   - Docker container privileges
   - File system permissions
   - Database user privileges
   - API rate limiting
   - Admin endpoint protection

   Files to review:
   - Dockerfile (USER directive)
   - main.py (rate limiting)
   - routes_*.py (admin endpoints)
   - database.py (connection string)

   SPECIFIC CHECKS:
   - Verify Docker runs as non-root
   - Check rate limiting on all endpoints
   - Validate admin endpoints require authentication
   - Look for overly permissive database grants

6. DEPENDENCY SECURITY (Priority: MEDIUM)
   - Known vulnerabilities in dependencies
   - Outdated packages
   - Supply chain risks

   Files to review:
   - requirements.txt
   - Dockerfile (base image)

   SPECIFIC CHECKS:
   - Check PyJWT version (CVE-2024-33663 in <2.9.0)
   - Check kiteconnect version for known issues
   - Verify base image is recent

7. ERROR HANDLING & INFORMATION DISCLOSURE (Priority: MEDIUM)
   - Stack traces in production
   - Verbose error messages
   - Debug mode exposure
   - Exception information leakage

   Files to review:
   - main.py (exception handlers)
   - routes_*.py (error responses)
   - config.py (debug settings)

   SPECIFIC CHECKS:
   - Search for stack traces in responses
   - Check if DEBUG=True in production
   - Verify exceptions are sanitized

8. SESSION & STATE MANAGEMENT (Priority: MEDIUM)
   - Session fixation risks
   - Token replay protection
   - Idempotency key security
   - State persistence security

   Files to review:
   - order_executor.py (idempotency)
   - routes_websocket.py (session binding)
   - jwt_auth.py (token revocation)

   SPECIFIC CHECKS:
   - Verify JWT tokens can be revoked
   - Check WebSocket tokens are bound to connections
   - Validate idempotency keys use secure hashing

ANALYSIS METHOD:

For EACH area:
1. Use `grep` to search for vulnerability patterns
2. Use `read` to analyze suspicious code sections
3. Use `bash` to check file permissions, dependency versions
4. Document vulnerabilities with file:line references and CWE mappings

VULNERABILITY ASSESSMENT:

For EACH vulnerability:
- **Severity**: CRITICAL / HIGH / MEDIUM / LOW
- **CVSS Score**: Calculate based on exploitability and impact
- **CWE/CVE**: Map to Common Weakness Enumeration
- **Exploitability**: Proof of concept or attack scenario
- **Impact**: Data loss, unauthorized access, financial loss, etc.

DELIVERABLE FORMAT:

Create `/docs/assessment_2/02_security_audit.md` containing:

## Executive Summary
- Total vulnerabilities: [CRITICAL: X, HIGH: Y, MEDIUM: Z, LOW: W]
- OWASP Top 10 mapping
- Compliance status (PCI-DSS, SOC 2)
- Deployment recommendation (BLOCK / CONDITIONAL / APPROVE)

## Vulnerability Matrix

| ID | Title | Severity | CVSS | CWE | File:Line | Status |
|----|-------|----------|------|-----|-----------|--------|
| CRITICAL-001 | [Title] | CRITICAL | 9.1 | CWE-XXX | file.py:123 | OPEN |

## Detailed Findings

For EACH vulnerability:

### [ID] [Vulnerability Title] (Severity: CRITICAL/HIGH/MEDIUM/LOW)

**CWE/CVE:** CWE-XXX / CVE-YYYY-NNNNN
**CVSS Score:** X.X (Vector: CVSS:3.1/AV:N/AC:L/...)
**File:** `path/to/file.py:line_number`

**Vulnerability Description:**
[Clear description of the security flaw]

**Attack Scenario:**
[Step-by-step exploitation scenario]

**Proof of Concept:**
```python
# Exploit code (if safe to demonstrate)
```

**Impact:**
- Confidentiality: [HIGH/MEDIUM/LOW/NONE]
- Integrity: [HIGH/MEDIUM/LOW/NONE]
- Availability: [HIGH/MEDIUM/LOW/NONE]
- Financial Risk: [$XX,XXX - $XXX,XXX]
- Compliance: [PCI-DSS violation, SOC 2 failure, etc.]

**Vulnerable Code:**
```python
[Current insecure code]
```

**Root Cause:**
[Why this vulnerability exists]

**Recommended Mitigation:**
[Specific, actionable fix]

**Secure Code:**
```python
[Fixed code with security best practices]
```

**Effort Estimate:** [Hours/Days]

**Validation Steps:**
1. [How to test the fix]
2. [How to verify security improvement]

**Functional Parity Guarantee:**
[Statement confirming zero behavioral change]

## Compliance Assessment

### PCI-DSS Requirements
- Requirement 1 (Firewall): [PASS/FAIL with details]
- Requirement 3 (Encryption): [PASS/FAIL with details]
- Requirement 6 (Secure Development): [PASS/FAIL with details]
- [Continue for all relevant requirements]

### SOC 2 Trust Principles
- Security: [PASS/FAIL with details]
- Availability: [PASS/FAIL with details]
- Confidentiality: [PASS/FAIL with details]

## Remediation Roadmap

**Phase 1 (CRITICAL - Block Production):**
- [List all CRITICAL vulnerabilities]
- Estimated effort: X days
- Must fix before any deployment

**Phase 2 (HIGH - Pre-Production):**
- [List all HIGH vulnerabilities]
- Estimated effort: Y days
- Must fix before production deployment

**Phase 3 (MEDIUM - Post-Deployment):**
- [List all MEDIUM vulnerabilities]
- Estimated effort: Z days

**Phase 4 (LOW - Hardening):**
- [List all LOW vulnerabilities]
- Estimated effort: W days

CRITICAL CONSTRAINTS:

1. ⚠️ **ZERO FUNCTIONAL IMPACT**: All security fixes MUST preserve behavior
2. 🔍 **EVIDENCE-BASED**: Every vulnerability must have file:line reference
3. 💰 **FINANCIAL RISK**: Quantify potential losses for trading system vulnerabilities
4. 📋 **COMPLIANCE**: Map to PCI-DSS and SOC 2 requirements
5. 🎯 **EXPLOITABLE**: Focus on real, exploitable vulnerabilities, not theoretical

SEVERITY DEFINITIONS:

- **CRITICAL**: Leads to complete system compromise, data theft, or significant financial loss. Fix immediately.
- **HIGH**: Allows unauthorized access, data manipulation, or service disruption. Fix before production.
- **MEDIUM**: Weakens security posture but requires multiple conditions to exploit. Fix soon.
- **LOW**: Minor security improvements or hardening. Fix when capacity allows.

OUTPUT REQUIREMENTS:

- Minimum 15-25 vulnerabilities identified with file:line refs
- Each vulnerability must have exploit scenario and mitigation
- OWASP Top 10 2021 coverage analysis
- PCI-DSS and SOC 2 compliance assessment
- Prioritized remediation roadmap with effort estimates
- Total effort estimate for all fixes

BEGIN AUDIT NOW.

Use all available tools (grep, read, bash) to conduct a thorough, evidence-based security review.
```

---

## Expected Output

A comprehensive security audit document (~120-180 KB) with:
- Executive summary with vulnerability counts
- OWASP Top 10 mapping
- 15-25 detailed vulnerabilities with file:line references
- Exploit scenarios and mitigations for each
- Compliance assessment (PCI-DSS, SOC 2)
- Prioritized remediation roadmap
- Total effort estimate (typically 5-15 developer days for all fixes)

---

## Success Criteria

✅ All vulnerabilities reference specific file:line locations
✅ Each vulnerability includes CWE/CVE mapping
✅ Exploit scenarios provided for all CRITICAL/HIGH issues
✅ Mitigations preserve 100% functional parity
✅ CVSS scores calculated for severity
✅ Compliance status assessed (PCI-DSS, SOC 2)
✅ Remediation roadmap with effort estimates

---

## Next Steps

After completion:
1. Review identified vulnerabilities with security team
2. Validate exploitability in staging environment
3. Prioritize fixes based on risk and effort
4. Proceed to **03_code_expert_review.md** (Code Quality Review)
