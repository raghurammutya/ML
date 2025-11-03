#!/usr/bin/env python3
"""
Comprehensive test suite for user_service

This script validates:
1. Import integrity
2. Schema validation
3. Service logic
4. API endpoint structure
"""

import sys
import traceback
from typing import List, Dict, Any

# Test results tracker
results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def test_result(test_name: str, passed: bool, message: str = ""):
    """Record test result"""
    if passed:
        results["passed"].append(test_name)
        print(f"✅ PASS: {test_name}")
    else:
        results["failed"].append((test_name, message))
        print(f"❌ FAIL: {test_name}")
        if message:
            print(f"   Error: {message}")

def warning(message: str):
    """Record warning"""
    results["warnings"].append(message)
    print(f"⚠️  WARNING: {message}")

print("=" * 80)
print("USER SERVICE - COMPREHENSIVE TEST SUITE")
print("=" * 80)
print()

# ============================================================================
# 1. TEST IMPORTS
# ============================================================================
print("1. Testing Imports...")
print("-" * 80)

# Test core imports
try:
    from app.core.config import settings
    test_result("Import: core.config", True)
except Exception as e:
    test_result("Import: core.config", False, str(e))

try:
    from app.core.database import get_db
    test_result("Import: core.database", True)
except Exception as e:
    test_result("Import: core.database", False, str(e))

try:
    from app.core.redis_client import RedisClient
    test_result("Import: core.redis_client", True)
except Exception as e:
    test_result("Import: core.redis_client", False, str(e))

# Test models
try:
    from app.models.user import User, Role, Permission, UserRole, UserPermission, AuthProvider
    test_result("Import: models.user", True)
except Exception as e:
    test_result("Import: models.user", False, str(e))

try:
    from app.models.trading_account import TradingAccount
    test_result("Import: models.trading_account", True)
except Exception as e:
    test_result("Import: models.trading_account", False, str(e))

# Test schemas
schemas_to_test = [
    "auth", "authz", "user", "mfa", "trading_account",
    "password_reset", "oauth", "audit"
]

for schema_name in schemas_to_test:
    try:
        module = __import__(f"app.schemas.{schema_name}", fromlist=["*"])
        test_result(f"Import: schemas.{schema_name}", True)
    except Exception as e:
        test_result(f"Import: schemas.{schema_name}", False, str(e))

# Test services
services_to_test = [
    "auth_service", "authz_service", "user_service", "mfa_service",
    "jwt_service", "kms_service", "trading_account_service",
    "password_reset_service", "oauth_service", "audit_service", "event_service"
]

for service_name in services_to_test:
    try:
        module = __import__(f"app.services.{service_name}", fromlist=["*"])
        test_result(f"Import: services.{service_name}", True)
    except Exception as e:
        test_result(f"Import: services.{service_name}", False, str(e))

# Test endpoints
endpoints_to_test = ["auth", "authz", "users", "mfa", "trading_accounts", "audit"]

for endpoint_name in endpoints_to_test:
    try:
        module = __import__(f"app.api.v1.endpoints.{endpoint_name}", fromlist=["router"])
        test_result(f"Import: endpoints.{endpoint_name}", True)
    except Exception as e:
        test_result(f"Import: endpoints.{endpoint_name}", False, str(e))

print()

# ============================================================================
# 2. TEST SCHEMAS
# ============================================================================
print("2. Testing Schemas...")
print("-" * 80)

try:
    from app.schemas.password_reset import (
        PasswordResetRequestRequest,
        PasswordResetRequestResponse,
        PasswordResetRequest,
        PasswordResetResponse
    )

    # Test schema creation
    req = PasswordResetRequestRequest(email="test@example.com")
    assert req.email == "test@example.com"

    resp = PasswordResetRequestResponse(email="test@example.com", expires_in_minutes=30)
    assert resp.expires_in_minutes == 30

    test_result("Schema: PasswordReset schemas", True)
except Exception as e:
    test_result("Schema: PasswordReset schemas", False, str(e))

try:
    from app.schemas.oauth import (
        OAuthInitiateRequest,
        OAuthInitiateResponse,
        OAuthCallbackRequest,
        OAuthCallbackResponse,
        OAuthUserInfo
    )

    # Test schema creation
    init_req = OAuthInitiateRequest(provider="google")
    assert init_req.provider == "google"

    user_info = OAuthUserInfo(
        email="test@example.com",
        name="Test User",
        email_verified=True,
        provider_user_id="12345",
        provider="google"
    )
    assert user_info.email_verified == True

    test_result("Schema: OAuth schemas", True)
except Exception as e:
    test_result("Schema: OAuth schemas", False, str(e))

try:
    from app.schemas.audit import (
        AuditEventResponse,
        GetAuditEventsRequest,
        GetAuditEventsResponse,
        ExportAuditEventsRequest,
        ExportAuditEventsResponse
    )

    # Test schema creation
    export_req = ExportAuditEventsRequest(format="json")
    assert export_req.format == "json"

    test_result("Schema: Audit schemas", True)
except Exception as e:
    test_result("Schema: Audit schemas", False, str(e))

print()

# ============================================================================
# 3. TEST SERVICE INSTANTIATION
# ============================================================================
print("3. Testing Service Classes...")
print("-" * 80)

try:
    from app.services.password_reset_service import PasswordResetService
    test_result("Service: PasswordResetService class", True)
except Exception as e:
    test_result("Service: PasswordResetService class", False, str(e))

try:
    from app.services.oauth_service import OAuthService
    test_result("Service: OAuthService class", True)
except Exception as e:
    test_result("Service: OAuthService class", False, str(e))

try:
    from app.services.audit_service import AuditService
    test_result("Service: AuditService class", True)
except Exception as e:
    test_result("Service: AuditService class", False, str(e))

print()

# ============================================================================
# 4. TEST API ENDPOINTS STRUCTURE
# ============================================================================
print("4. Testing API Endpoint Structure...")
print("-" * 80)

try:
    from app.api.v1.endpoints.auth import router as auth_router

    # Count routes
    route_count = len(auth_router.routes)
    expected_count = 12  # We expect 12 auth endpoints

    if route_count >= expected_count:
        test_result(f"Auth endpoints count ({route_count})", True)
    else:
        test_result(f"Auth endpoints count ({route_count})", False,
                   f"Expected at least {expected_count}, got {route_count}")

    # Check for specific endpoints
    route_paths = [route.path for route in auth_router.routes]

    expected_paths = [
        "/register",
        "/login",
        "/mfa/verify",
        "/refresh",
        "/logout",
        "/sessions",
        "/password/reset-request",
        "/password/reset",
        "/oauth/google",
        "/oauth/google/callback",
        "/.well-known/jwks.json"
    ]

    for path in expected_paths:
        if any(path in route_path for route_path in route_paths):
            test_result(f"Auth route: {path}", True)
        else:
            test_result(f"Auth route: {path}", False, "Route not found")

except Exception as e:
    test_result("Auth endpoints structure", False, str(e))

try:
    from app.api.v1.endpoints.audit import router as audit_router

    route_count = len(audit_router.routes)
    expected_count = 3  # We expect 3 audit endpoints

    if route_count >= expected_count:
        test_result(f"Audit endpoints count ({route_count})", True)
    else:
        test_result(f"Audit endpoints count ({route_count})", False,
                   f"Expected at least {expected_count}, got {route_count}")

except Exception as e:
    test_result("Audit endpoints structure", False, str(e))

print()

# ============================================================================
# 5. TEST MAIN APP
# ============================================================================
print("5. Testing Main Application...")
print("-" * 80)

try:
    from app.main import app
    test_result("Main app import", True)

    # Check routers are included
    route_paths = [route.path for route in app.routes]

    expected_prefixes = [
        "/v1/auth",
        "/v1/authz",
        "/v1/users",
        "/v1/mfa",
        "/v1/trading-accounts",
        "/v1/audit"
    ]

    for prefix in expected_prefixes:
        if any(prefix in path for path in route_paths):
            test_result(f"Router included: {prefix}", True)
        else:
            test_result(f"Router included: {prefix}", False, "Router not found")

except Exception as e:
    test_result("Main app", False, str(e))

print()

# ============================================================================
# 6. TEST CONFIGURATION
# ============================================================================
print("6. Testing Configuration...")
print("-" * 80)

try:
    from app.core.config import settings

    # Check critical settings exist
    critical_settings = [
        "APP_NAME",
        "VERSION",
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SIGNING_KEY_ID",
        "JWT_ACCESS_TOKEN_TTL_MINUTES",
        "JWT_REFRESH_TOKEN_TTL_DAYS",
        "PASSWORD_MIN_LENGTH",
        "PASSWORD_RESET_TOKEN_TTL_MINUTES",
        "SESSION_COOKIE_NAME",
        "CORS_ALLOWED_ORIGINS"
    ]

    for setting_name in critical_settings:
        if hasattr(settings, setting_name):
            test_result(f"Config: {setting_name}", True)
        else:
            test_result(f"Config: {setting_name}", False, "Setting not found")

except Exception as e:
    test_result("Configuration", False, str(e))

print()

# ============================================================================
# 7. TEST UTILITY FUNCTIONS
# ============================================================================
print("7. Testing Utility Functions...")
print("-" * 80)

try:
    from app.utils.security import (
        hash_password,
        verify_password,
        validate_password_strength,
        generate_device_fingerprint
    )

    # Test password hashing
    password = "TestPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)

    test_result("Utility: Password hashing", True)

    # Test password validation
    validation = validate_password_strength("Weak", ["test@example.com"])
    assert not validation["valid"]

    validation = validate_password_strength("StrongPassword123!", ["test@example.com"])
    assert validation["valid"]

    test_result("Utility: Password validation", True)

    # Test device fingerprint
    fingerprint = generate_device_fingerprint("Mozilla/5.0", "192.168.1.1")
    assert len(fingerprint) > 0

    test_result("Utility: Device fingerprint", True)

except Exception as e:
    test_result("Utility functions", False, str(e))

print()

# ============================================================================
# GENERATE REPORT
# ============================================================================
print("=" * 80)
print("TEST REPORT")
print("=" * 80)
print()

total_tests = len(results["passed"]) + len(results["failed"])
pass_rate = (len(results["passed"]) / total_tests * 100) if total_tests > 0 else 0

print(f"Total Tests: {total_tests}")
print(f"Passed: {len(results['passed'])} ✅")
print(f"Failed: {len(results['failed'])} ❌")
print(f"Warnings: {len(results['warnings'])} ⚠️")
print(f"Pass Rate: {pass_rate:.1f}%")
print()

if results["failed"]:
    print("Failed Tests:")
    print("-" * 80)
    for test_name, error in results["failed"]:
        print(f"  ❌ {test_name}")
        if error:
            print(f"     {error}")
    print()

if results["warnings"]:
    print("Warnings:")
    print("-" * 80)
    for warning in results["warnings"]:
        print(f"  ⚠️  {warning}")
    print()

print("=" * 80)

# Exit with appropriate code
if len(results["failed"]) > 0:
    print("❌ SOME TESTS FAILED")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
    sys.exit(0)
