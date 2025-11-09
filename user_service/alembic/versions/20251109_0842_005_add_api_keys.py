"""Add API keys tables

Revision ID: 005
Revises: 004
Create Date: 2025-11-09 08:42:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create rate_limit_tier enum
    op.execute("CREATE TYPE ratelimittier AS ENUM ('free', 'standard', 'premium', 'unlimited')")

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('api_key_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('key_prefix', sa.String(length=20), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='["read"]'),
        sa.Column('ip_whitelist', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rate_limit_tier', sa.Enum('free', 'standard', 'premium', 'unlimited', name='ratelimittier'), nullable=False, server_default='standard'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_ip', sa.String(length=45), nullable=True),
        sa.Column('usage_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_by', sa.BigInteger(), nullable=True),
        sa.Column('revoked_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['revoked_by'], ['users.user_id']),
        sa.PrimaryKeyConstraint('api_key_id'),
        sa.UniqueConstraint('key_prefix', name='uq_api_keys_key_prefix')
    )

    # Create indexes
    op.create_index(op.f('ix_api_keys_api_key_id'), 'api_keys', ['api_key_id'], unique=False)
    op.create_index('idx_api_keys_user_id', 'api_keys', ['user_id'], unique=False)
    op.create_index(
        'idx_api_keys_key_prefix_active',
        'api_keys',
        ['key_prefix'],
        unique=False,
        postgresql_where=sa.text('revoked_at IS NULL')
    )
    op.create_index(
        'idx_api_keys_expires_at',
        'api_keys',
        ['expires_at'],
        unique=False,
        postgresql_where=sa.text('revoked_at IS NULL AND expires_at IS NOT NULL')
    )

    # Create api_key_usage_logs table
    op.create_table(
        'api_key_usage_logs',
        sa.Column('log_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('api_key_id', sa.BigInteger(), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.api_key_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('log_id')
    )

    # Create indexes for usage logs
    op.create_index(op.f('ix_api_key_usage_logs_log_id'), 'api_key_usage_logs', ['log_id'], unique=False)
    op.create_index('idx_api_key_usage_api_key_id', 'api_key_usage_logs', ['api_key_id', 'timestamp'], unique=False)
    op.create_index('idx_api_key_usage_timestamp', 'api_key_usage_logs', ['timestamp'], unique=False)

    # Convert api_key_usage_logs to TimescaleDB hypertable (if TimescaleDB is available)
    # This is optional and will only work if TimescaleDB extension is installed
    try:
        op.execute("SELECT create_hypertable('api_key_usage_logs', 'timestamp', if_not_exists => TRUE)")
    except Exception:
        # TimescaleDB not available, skip hypertable creation
        pass


def downgrade() -> None:
    # Drop tables
    op.drop_index('idx_api_key_usage_timestamp', table_name='api_key_usage_logs')
    op.drop_index('idx_api_key_usage_api_key_id', table_name='api_key_usage_logs')
    op.drop_index(op.f('ix_api_key_usage_logs_log_id'), table_name='api_key_usage_logs')
    op.drop_table('api_key_usage_logs')

    op.drop_index('idx_api_keys_expires_at', table_name='api_keys')
    op.drop_index('idx_api_keys_key_prefix_active', table_name='api_keys')
    op.drop_index('idx_api_keys_user_id', table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_api_key_id'), table_name='api_keys')
    op.drop_table('api_keys')

    # Drop enum type
    op.execute('DROP TYPE ratelimittier')
