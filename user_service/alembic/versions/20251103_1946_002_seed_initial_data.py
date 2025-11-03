"""Seed initial data - roles, policies, service clients

Revision ID: 002
Revises: 001
Create Date: 2025-11-03 19:46:00

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Insert default roles
    op.execute("""
        INSERT INTO roles (name, description, created_at) VALUES
        ('user', 'Standard user role with basic permissions', NOW()),
        ('admin', 'Administrator with full system access', NOW()),
        ('compliance', 'Compliance officer with audit access', NOW())
        ON CONFLICT (name) DO NOTHING
    """)

    # Insert default policies
    op.execute("""
        INSERT INTO policies (name, effect, subjects, actions, resources, conditions, priority, enabled, created_at, updated_at)
        VALUES
        (
            'Trading Account Owner Can Trade',
            'ALLOW',
            '["user:*"]'::jsonb,
            '["trade:place_order", "trade:cancel_order", "trade:modify_order"]'::jsonb,
            '["trading_account:*"]'::jsonb,
            '{"owner": true, "account_status": "active"}'::jsonb,
            100,
            true,
            NOW(),
            NOW()
        ),
        (
            'Trading Account Member Can Read',
            'ALLOW',
            '["user:*"]'::jsonb,
            '["read:account", "read:positions", "read:orders"]'::jsonb,
            '["trading_account:*"]'::jsonb,
            '{"member": true, "account_status": "active"}'::jsonb,
            90,
            true,
            NOW(),
            NOW()
        ),
        (
            'Admin Full Access',
            'ALLOW',
            '["role:admin"]'::jsonb,
            '["*"]'::jsonb,
            '["*"]'::jsonb,
            '{}'::jsonb,
            1000,
            true,
            NOW(),
            NOW()
        ),
        (
            'Compliance Audit Access',
            'ALLOW',
            '["role:compliance"]'::jsonb,
            '["read:audit", "export:audit"]'::jsonb,
            '["audit:*"]'::jsonb,
            '{}'::jsonb,
            500,
            true,
            NOW(),
            NOW()
        ),
        (
            'User Self Profile Access',
            'ALLOW',
            '["user:*"]'::jsonb,
            '["read:profile", "update:profile", "read:preferences", "update:preferences"]'::jsonb,
            '["user:self"]'::jsonb,
            '{"subject_match": true}'::jsonb,
            200,
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (name) DO NOTHING
    """)

    # Insert service clients (Note: Replace these hashes with actual bcrypt hashes in production)
    # These are placeholder hashes for 'development_secret'
    op.execute("""
        INSERT INTO oauth_clients (client_id, client_secret_hash, name, scopes, enabled, created_at)
        VALUES
        (
            'service_ticker',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lW4tLrJgqZPK',
            'Ticker Service',
            '["authz:check", "credentials:read"]'::jsonb,
            true,
            NOW()
        ),
        (
            'service_alert',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lW4tLrJgqZPK',
            'Alert Service',
            '["authz:check"]'::jsonb,
            true,
            NOW()
        ),
        (
            'service_backend',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lW4tLrJgqZPK',
            'Backend Service',
            '["authz:check", "user:read"]'::jsonb,
            true,
            NOW()
        ),
        (
            'service_calendar',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lW4tLrJgqZPK',
            'Calendar Service',
            '["authz:check"]'::jsonb,
            true,
            NOW()
        )
        ON CONFLICT (client_id) DO NOTHING
    """)


def downgrade() -> None:
    # Remove seeded data
    op.execute("DELETE FROM oauth_clients WHERE client_id IN ('service_ticker', 'service_alert', 'service_backend', 'service_calendar')")
    op.execute("DELETE FROM policies WHERE name IN ('Trading Account Owner Can Trade', 'Trading Account Member Can Read', 'Admin Full Access', 'Compliance Audit Access', 'User Self Profile Access')")
    op.execute("DELETE FROM roles WHERE name IN ('user', 'admin', 'compliance')")
