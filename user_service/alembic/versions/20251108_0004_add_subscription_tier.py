"""Add subscription tier tracking to trading accounts

Revision ID: 20251108_0004
Revises: 20251107_0003
Create Date: 2025-11-08 19:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251108_0004'
down_revision = '20251107_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add subscription tier columns to trading_accounts table"""

    # Create subscription tier enum type
    subscription_tier_enum = postgresql.ENUM(
        'unknown', 'personal', 'connect', 'startup',
        name='subscriptiontier',
        create_type=True
    )
    subscription_tier_enum.create(op.get_bind(), checkfirst=True)

    # Add subscription tier columns
    op.add_column(
        'trading_accounts',
        sa.Column(
            'subscription_tier',
            sa.Enum('unknown', 'personal', 'connect', 'startup', name='subscriptiontier'),
            nullable=False,
            server_default='unknown'
        )
    )

    op.add_column(
        'trading_accounts',
        sa.Column(
            'subscription_tier_last_checked',
            sa.DateTime(),
            nullable=True
        )
    )

    op.add_column(
        'trading_accounts',
        sa.Column(
            'market_data_available',
            sa.Boolean(),
            nullable=False,
            server_default='false'
        )
    )

    # Create index for querying accounts with market data
    op.create_index(
        'idx_trading_accounts_market_data',
        'trading_accounts',
        ['market_data_available', 'status'],
        unique=False
    )

    # Create index for subscription tier
    op.create_index(
        'idx_trading_accounts_subscription_tier',
        'trading_accounts',
        ['subscription_tier'],
        unique=False
    )


def downgrade() -> None:
    """Remove subscription tier columns from trading_accounts table"""

    # Drop indexes
    op.drop_index('idx_trading_accounts_subscription_tier', table_name='trading_accounts')
    op.drop_index('idx_trading_accounts_market_data', table_name='trading_accounts')

    # Drop columns
    op.drop_column('trading_accounts', 'market_data_available')
    op.drop_column('trading_accounts', 'subscription_tier_last_checked')
    op.drop_column('trading_accounts', 'subscription_tier')

    # Drop enum type
    sa.Enum(name='subscriptiontier').drop(op.get_bind(), checkfirst=True)
