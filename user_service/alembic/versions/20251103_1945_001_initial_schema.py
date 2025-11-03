"""Initial schema - create all tables

Revision ID: 001
Revises:
Create Date: 2025-11-03 19:45:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('role_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('role_id')
    )
    op.create_index(op.f('ix_roles_role_id'), 'roles', ['role_id'], unique=False)
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('user_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('phone_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('locale', sa.String(length=10), nullable=False, server_default='en-US'),
        sa.Column('status', sa.Enum('PENDING_VERIFICATION', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED', name='userstatus'), nullable=False, server_default='PENDING_VERIFICATION'),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('oauth_provider', sa.String(length=50), nullable=True),
        sa.Column('oauth_subject', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_status'), 'users', ['status'], unique=False)
    op.create_index(op.f('ix_users_oauth'), 'users', ['oauth_provider', 'oauth_subject'], unique=False, postgresql_where=sa.text('oauth_provider IS NOT NULL'))

    # Create user_roles table
    op.create_table(
        'user_roles',
        sa.Column('user_role_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('granted_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('user_role_id'),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_role')
    )
    op.create_index(op.f('ix_user_roles_user_role_id'), 'user_roles', ['user_role_id'], unique=False)
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)

    # Create user_preferences table
    op.create_table(
        'user_preferences',
        sa.Column('preference_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('default_trading_account_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('preference_id'),
        sa.UniqueConstraint('user_id', name='uq_user_preference')
    )
    op.create_index(op.f('ix_user_preferences_preference_id'), 'user_preferences', ['preference_id'], unique=False)
    op.create_index(op.f('ix_user_preferences_user_id'), 'user_preferences', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_preferences_jsonb'), 'user_preferences', ['preferences'], unique=False, postgresql_using='gin')

    # Create trading_accounts table
    op.create_table(
        'trading_accounts',
        sa.Column('trading_account_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('broker', sa.String(length=50), nullable=False),
        sa.Column('nickname', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('PENDING_VERIFICATION', 'ACTIVE', 'CREDENTIALS_EXPIRED', 'DEACTIVATED', name='tradingaccountstatus'), nullable=False, server_default='PENDING_VERIFICATION'),
        sa.Column('broker_profile_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('credential_vault_ref', sa.String(length=255), nullable=False),
        sa.Column('data_key_wrapped', sa.Text(), nullable=False),
        sa.Column('linked_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('trading_account_id')
    )
    op.create_index(op.f('ix_trading_accounts_trading_account_id'), 'trading_accounts', ['trading_account_id'], unique=False)
    op.create_index(op.f('ix_trading_accounts_user_id'), 'trading_accounts', ['user_id'], unique=False)
    op.create_index(op.f('ix_trading_accounts_status'), 'trading_accounts', ['status'], unique=False)

    # Create trading_account_memberships table
    op.create_table(
        'trading_account_memberships',
        sa.Column('membership_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('trading_account_id', sa.BigInteger(), nullable=False),
        sa.Column('member_user_id', sa.BigInteger(), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='["read"]'),
        sa.Column('granted_by', sa.BigInteger(), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trading_account_id'], ['trading_accounts.trading_account_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('membership_id'),
        sa.UniqueConstraint('trading_account_id', 'member_user_id', name='uq_account_member')
    )
    op.create_index(op.f('ix_memberships_membership_id'), 'trading_account_memberships', ['membership_id'], unique=False)
    op.create_index(op.f('ix_memberships_account'), 'trading_account_memberships', ['trading_account_id'], unique=False)
    op.create_index(op.f('ix_memberships_member'), 'trading_account_memberships', ['member_user_id'], unique=False)

    # Create mfa_totp table
    op.create_table(
        'mfa_totp',
        sa.Column('totp_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('secret_encrypted', sa.Text(), nullable=False),
        sa.Column('backup_codes_encrypted', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('totp_id'),
        sa.UniqueConstraint('user_id', name='uq_mfa_totp_user')
    )
    op.create_index(op.f('ix_mfa_totp_totp_id'), 'mfa_totp', ['totp_id'], unique=False)

    # Create policies table
    op.create_table(
        'policies',
        sa.Column('policy_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('effect', sa.Enum('ALLOW', 'DENY', name='policyeffect'), nullable=False, server_default='ALLOW'),
        sa.Column('subjects', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('resources', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('policy_id')
    )
    op.create_index(op.f('ix_policies_policy_id'), 'policies', ['policy_id'], unique=False)
    op.create_index(op.f('ix_policies_name'), 'policies', ['name'], unique=True)
    op.create_index(op.f('ix_policies_enabled'), 'policies', ['enabled'], unique=False)

    # Create oauth_clients table
    op.create_table(
        'oauth_clients',
        sa.Column('client_id', sa.String(length=100), nullable=False),
        sa.Column('client_secret_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='["authz:check"]'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('client_id')
    )

    # Create jwt_signing_keys table
    op.create_table(
        'jwt_signing_keys',
        sa.Column('key_id', sa.String(length=50), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('private_key_encrypted', sa.Text(), nullable=False),
        sa.Column('algorithm', sa.String(length=10), nullable=False, server_default='RS256'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('rotated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('key_id')
    )
    op.create_index(op.f('ix_jwt_signing_keys_active'), 'jwt_signing_keys', ['active'], unique=True, postgresql_where=sa.text('active = true'))

    # Create auth_events table (TimescaleDB hypertable will be created in a separate step)
    op.create_table(
        'auth_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('ip', postgresql.INET(), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('device_fingerprint', sa.String(length=255), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('risk_score', sa.String(length=20), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('notification_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('event_id')
    )
    op.create_index(op.f('ix_auth_events_event_id'), 'auth_events', ['event_id'], unique=False)
    op.create_index(op.f('ix_auth_events_timestamp'), 'auth_events', ['timestamp'], unique=False)
    op.create_index(op.f('ix_auth_events_user_timestamp'), 'auth_events', ['user_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_auth_events_type_timestamp'), 'auth_events', ['event_type', 'timestamp'], unique=False)
    op.create_index(op.f('ix_auth_events_session'), 'auth_events', ['session_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_auth_events_risk'), 'auth_events', ['risk_score'], unique=False, postgresql_where=sa.text("risk_score = 'high'"))

    # Note: TimescaleDB hypertable conversion will be done in a post-deployment SQL script
    # This is because it requires TimescaleDB extension to be installed


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('auth_events')
    op.drop_table('jwt_signing_keys')
    op.drop_table('oauth_clients')
    op.drop_table('policies')
    op.drop_table('mfa_totp')
    op.drop_table('trading_account_memberships')
    op.drop_table('trading_accounts')
    op.drop_table('user_preferences')
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('roles')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS userstatus')
    op.execute('DROP TYPE IF EXISTS tradingaccountstatus')
    op.execute('DROP TYPE IF EXISTS policyeffect')
