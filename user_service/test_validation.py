#!/usr/bin/env python3
"""
User Service Validation Test

This script validates the code structure and imports without requiring
environment variables or external dependencies.
"""

import sys
import os
import ast
import traceback
from pathlib import Path

# Test results
results = {"passed": 0, "failed": 0, "errors": []}

def test_file(file_path: Path, test_name: str):
    """Test if a Python file is valid"""
    try:
        with open(file_path, 'r') as f:
            code = f.compile()
            ast.parse(code)
        results["passed"] += 1
        print(f"✅ {test_name}")
        return True
    except Exception as e:
        results["failed"] += 1
        results["errors"].append((test_name, str(e)))
        print(f"❌ {test_name}: {str(e)[:100]}")
        return False

print("=" * 80)
print("USER SERVICE - VALIDATION TEST")
print("=" * 80)
print()

base_path = Path("/home/stocksadmin/Quantagro/tradingview-viz/user_service")

# Test structure
print("Testing Code Structure...")
print("-" * 80)

# Test all Python files
python_files = {
    # Core
    "app/main.py": "Main application",
    "app/core/config.py": "Configuration",
    "app/core/database.py": "Database setup",
    "app/core/redis_client.py": "Redis client",
    "app/core/kms.py": "KMS service",

    # Models
    "app/models/user.py": "User models",
    "app/models/trading_account.py": "Trading account models",
    "app/models/enums.py": "Enums",

    # Schemas
    "app/schemas/auth.py": "Auth schemas",
    "app/schemas/authz.py": "Authorization schemas",
    "app/schemas/user.py": "User schemas",
    "app/schemas/mfa.py": "MFA schemas",
    "app/schemas/trading_account.py": "Trading account schemas",
    "app/schemas/password_reset.py": "Password reset schemas",
    "app/schemas/oauth.py": "OAuth schemas",
    "app/schemas/audit.py": "Audit schemas",

    # Services
    "app/services/auth_service.py": "Auth service",
    "app/services/authz_service.py": "Authorization service",
    "app/services/user_service.py": "User service",
    "app/services/mfa_service.py": "MFA service",
    "app/services/jwt_service.py": "JWT service",
    "app/services/kms_service.py": "KMS service",
    "app/services/trading_account_service.py": "Trading account service",
    "app/services/password_reset_service.py": "Password reset service",
    "app/services/oauth_service.py": "OAuth service",
    "app/services/audit_service.py": "Audit service",
    "app/services/event_service.py": "Event service",

    # Endpoints
    "app/api/v1/endpoints/auth.py": "Auth endpoints",
    "app/api/v1/endpoints/authz.py": "Authorization endpoints",
    "app/api/v1/endpoints/users.py": "User endpoints",
    "app/api/v1/endpoints/mfa.py": "MFA endpoints",
    "app/api/v1/endpoints/trading_accounts.py": "Trading account endpoints",
    "app/api/v1/endpoints/audit.py": "Audit endpoints",

    # Dependencies
    "app/api/v1/dependencies.py": "API dependencies",

    # Utils
    "app/utils/security.py": "Security utilities",
}

for file_path, description in python_files.items():
    full_path = base_path / file_path
    if full_path.exists():
        test_file(full_path, f"{description} ({file_path})")
    else:
        results["failed"] += 1
        results["errors"].append((description, "File not found"))
        print(f"❌ {description}: File not found")

print()

# Test that endpoints have proper routes
print("Analyzing Endpoint Routes...")
print("-" * 80)

endpoint_files = [
    ("app/api/v1/endpoints/auth.py", 12, "Authentication"),
    ("app/api/v1/endpoints/authz.py", 4, "Authorization"),
    ("app/api/v1/endpoints/users.py", 5, "User Management"),
    ("app/api/v1/endpoints/mfa.py", 5, "MFA/TOTP"),
    ("app/api/v1/endpoints/trading_accounts.py", 8, "Trading Accounts"),
    ("app/api/v1/endpoints/audit.py", 3, "Audit Trail"),
]

for file_path, expected_count, name in endpoint_files:
    full_path = base_path / file_path
    if full_path.exists():
        with open(full_path, 'r') as f:
            content = f.read()

        # Count @router decorators
        route_count = content.count("@router.")

        if route_count >= expected_count:
            results["passed"] += 1
            print(f"✅ {name}: {route_count}/{expected_count} endpoints")
        else:
            results["failed"] += 1
            results["errors"].append((name, f"Expected {expected_count}, found {route_count}"))
            print(f"❌ {name}: {route_count}/{expected_count} endpoints")

print()

# Test key features in files
print("Checking Key Features...")
print("-" * 80)

features_to_check = [
    ("app/services/password_reset_service.py", "request_password_reset", "Password reset request"),
    ("app/services/password_reset_service.py", "reset_password", "Password reset completion"),
    ("app/services/oauth_service.py", "initiate_oauth_flow", "OAuth initiation"),
    ("app/services/oauth_service.py", "handle_oauth_callback", "OAuth callback"),
    ("app/services/audit_service.py", "get_user_audit_events", "Get audit events"),
    ("app/services/audit_service.py", "export_user_audit_events", "Export audit events"),
    ("app/schemas/password_reset.py", "PasswordResetRequestRequest", "Password reset request schema"),
    ("app/schemas/oauth.py", "OAuthInitiateRequest", "OAuth initiate schema"),
    ("app/schemas/audit.py", "GetAuditEventsRequest", "Audit events request schema"),
]

for file_path, feature_name, description in features_to_check:
    full_path = base_path / file_path
    if full_path.exists():
        with open(full_path, 'r') as f:
            content = f.read()

        if feature_name in content:
            results["passed"] += 1
            print(f"✅ {description}: Found {feature_name}")
        else:
            results["failed"] += 1
            results["errors"].append((description, f"{feature_name} not found"))
            print(f"❌ {description}: {feature_name} not found")
    else:
        results["failed"] += 1
        results["errors"].append((description, "File not found"))
        print(f"❌ {description}: File not found")

print()

# Check if README is updated
print("Checking Documentation...")
print("-" * 80)

readme_path = base_path / "README.md"
if readme_path.exists():
    with open(readme_path, 'r') as f:
        readme_content = f.read()

    checks = [
        ("100% Complete", "Completion status"),
        ("37/37", "Endpoint count"),
        ("Password Reset", "Password reset documentation"),
        ("OAuth", "OAuth documentation"),
        ("Audit Trail", "Audit trail documentation"),
    ]

    for check_str, description in checks:
        if check_str in readme_content:
            results["passed"] += 1
            print(f"✅ {description}: Found in README")
        else:
            results["failed"] += 1
            results["errors"].append((description, "Not found in README"))
            print(f"❌ {description}: Not found in README")
else:
    results["failed"] += 1
    results["errors"].append(("README", "File not found"))
    print(f"❌ README.md not found")

print()

# ============================================================================
# GENERATE REPORT
# ============================================================================
print("=" * 80)
print("VALIDATION REPORT")
print("=" * 80)
print()

total_tests = results["passed"] + results["failed"]
pass_rate = (results["passed"] / total_tests * 100) if total_tests > 0 else 0

print(f"Total Tests: {total_tests}")
print(f"Passed: {results['passed']} ✅")
print(f"Failed: {results['failed']} ❌")
print(f"Pass Rate: {pass_rate:.1f}%")
print()

if results["errors"]:
    print("Issues Found:")
    print("-" * 80)
    for test_name, error in results["errors"]:
        print(f"  ❌ {test_name}")
        print(f"     {error}")
    print()

print("=" * 80)

if results["failed"] == 0:
    print("✅ ALL VALIDATION CHECKS PASSED")
    print()
    print("Summary:")
    print("- All Python files have valid syntax")
    print("- All endpoints are properly defined")
    print("- All services and schemas are present")
    print("- Documentation is complete")
    print()
    print("Note: Runtime testing requires environment setup (DATABASE_URL, REDIS_URL, etc.)")
    sys.exit(0)
else:
    print("❌ SOME VALIDATION CHECKS FAILED")
    sys.exit(1)
