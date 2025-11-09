"""
Prometheus metrics for user_service.

Provides comprehensive observability metrics for monitoring:
- HTTP requests and performance
- Authentication and authorization
- User management operations
- Organization operations
- Trading account management
- Database and cache performance
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ============================================================================
# Application Info
# ============================================================================

app_info = Info('user_service', 'User service application info')

# ============================================================================
# HTTP Metrics
# ============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    ['method', 'endpoint']
)

# ============================================================================
# Authentication Metrics
# ============================================================================

auth_login_attempts_total = Counter(
    'auth_login_attempts_total',
    'Total login attempts',
    ['status']  # success, invalid_credentials, mfa_required, account_locked
)

auth_mfa_verifications_total = Counter(
    'auth_mfa_verifications_total',
    'Total MFA verification attempts',
    ['status']  # success, invalid_code, expired_code
)

auth_token_operations_total = Counter(
    'auth_token_operations_total',
    'Total token operations',
    ['operation', 'status']  # operation: create, refresh, revoke, validate
)

auth_api_key_operations_total = Counter(
    'auth_api_key_operations_total',
    'Total API key operations',
    ['operation', 'status']  # operation: create, revoke, validate
)

auth_active_sessions = Gauge(
    'auth_active_sessions',
    'Number of currently active user sessions'
)

# ============================================================================
# User Management Metrics
# ============================================================================

user_registrations_total = Counter(
    'user_registrations_total',
    'Total user registrations',
    ['status']  # success, email_exists, validation_error
)

user_email_verifications_total = Counter(
    'user_email_verifications_total',
    'Total email verification attempts',
    ['status']  # success, invalid_token, expired_token
)

user_password_resets_total = Counter(
    'user_password_resets_total',
    'Total password reset operations',
    ['operation', 'status']  # operation: request, complete
)

user_profile_updates_total = Counter(
    'user_profile_updates_total',
    'Total user profile updates',
    ['status']
)

users_total = Gauge(
    'users_total',
    'Total number of users',
    ['status']  # active, inactive, locked
)

# ============================================================================
# Organization Metrics
# ============================================================================

organization_operations_total = Counter(
    'organization_operations_total',
    'Total organization operations',
    ['operation', 'status']  # operation: create, update, deactivate, get, list
)

organization_member_operations_total = Counter(
    'organization_member_operations_total',
    'Total organization member operations',
    ['operation', 'status']  # operation: add, update, remove, list
)

organization_invitation_operations_total = Counter(
    'organization_invitation_operations_total',
    'Total organization invitation operations',
    ['operation', 'status']  # operation: create, accept, reject
)

organizations_total = Gauge(
    'organizations_total',
    'Total number of organizations',
    ['status']  # active, inactive
)

organization_members_total = Gauge(
    'organization_members_total',
    'Total number of organization members',
    ['role']  # owner, admin, member, viewer
)

organization_pending_invitations = Gauge(
    'organization_pending_invitations',
    'Number of pending organization invitations'
)

# ============================================================================
# Trading Account Metrics
# ============================================================================

trading_account_operations_total = Counter(
    'trading_account_operations_total',
    'Total trading account operations',
    ['operation', 'status']  # operation: create, update, link, unlink, list
)

trading_account_broker_operations_total = Counter(
    'trading_account_broker_operations_total',
    'Total broker-specific operations',
    ['broker', 'operation', 'status']  # broker: zerodha, operation: link, auth_callback
)

trading_accounts_total = Gauge(
    'trading_accounts_total',
    'Total number of trading accounts',
    ['broker', 'status']  # broker: zerodha, status: active, inactive
)

trading_account_subscription_tiers = Gauge(
    'trading_account_subscription_tiers',
    'Number of trading accounts by subscription tier',
    ['tier']  # unknown, connect, standard, historical, full
)

# ============================================================================
# Account Sharing Metrics
# ============================================================================

account_sharing_operations_total = Counter(
    'account_sharing_operations_total',
    'Total account sharing operations',
    ['operation', 'status']  # operation: add_member, update_member, remove_member
)

shared_account_members_total = Gauge(
    'shared_account_members_total',
    'Total number of shared account members',
    ['permission_level']  # view_only, trade_enabled, full_access
)

# ============================================================================
# Database Metrics
# ============================================================================

database_queries_total = Counter(
    'database_queries_total',
    'Total database queries executed',
    ['operation', 'table', 'status']  # operation: select, insert, update, delete
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation', 'table'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

database_connections = Gauge(
    'database_connections',
    'Number of database connections',
    ['state']  # active, idle, waiting
)

database_pool_size = Gauge(
    'database_pool_size',
    'Database connection pool size',
    ['type']  # total, available, in_use
)

# ============================================================================
# Redis/Cache Metrics
# ============================================================================

cache_operations_total = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'status']  # operation: get, set, delete, status: hit, miss, success, error
)

cache_operation_duration_seconds = Histogram(
    'cache_operation_duration_seconds',
    'Cache operation duration in seconds',
    ['operation'],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

cache_keys_total = Gauge(
    'cache_keys_total',
    'Total number of keys in cache',
    ['key_type']  # session, token, user_data, etc.
)

cache_memory_bytes = Gauge(
    'cache_memory_bytes',
    'Cache memory usage in bytes'
)

# ============================================================================
# Email Metrics
# ============================================================================

email_operations_total = Counter(
    'email_operations_total',
    'Total email operations',
    ['email_type', 'status']  # email_type: verification, password_reset, invitation, etc.
)

email_queue_size = Gauge(
    'email_queue_size',
    'Number of emails waiting to be sent'
)

# ============================================================================
# Error Metrics
# ============================================================================

errors_total = Counter(
    'errors_total',
    'Total errors encountered',
    ['error_type', 'severity']  # severity: warning, error, critical
)

validation_errors_total = Counter(
    'validation_errors_total',
    'Total validation errors',
    ['field', 'error_type']
)

# ============================================================================
# Business Metrics
# ============================================================================

daily_active_users = Gauge(
    'daily_active_users',
    'Number of unique users active in the last 24 hours'
)

monthly_active_users = Gauge(
    'monthly_active_users',
    'Number of unique users active in the last 30 days'
)

api_key_usage_total = Counter(
    'api_key_usage_total',
    'Total API requests using API keys',
    ['api_key_id', 'endpoint']
)
