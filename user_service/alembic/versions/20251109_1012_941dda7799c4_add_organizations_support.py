"""Add organizations support

Revision ID: 941dda7799c4
Revises: 005
Create Date: 2025-11-09 10:12:16.505254

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '941dda7799c4'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create organizations table
    op.create_table(
        'organizations',
        sa.Column('organization_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('website', sa.String(length=500), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED', name='organizationstatus'), nullable=False),
        sa.Column('settings', sa.dialects.postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_user_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('organization_id')
    )
    op.create_index('idx_organizations_slug', 'organizations', ['slug'], unique=False)
    op.create_index('idx_organizations_status', 'organizations', ['status'], unique=False)
    op.create_index('idx_organizations_created_by', 'organizations', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_organizations_organization_id'), 'organizations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_organizations_slug'), 'organizations', ['slug'], unique=True)

    # Create organization_members table
    op.create_table(
        'organization_members',
        sa.Column('membership_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role', sa.Enum('OWNER', 'ADMIN', 'MEMBER', 'VIEWER', name='organizationmemberrole'), nullable=False),
        sa.Column('custom_permissions', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('invited_by', sa.BigInteger(), nullable=True),
        sa.Column('invited_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('joined_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('removed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.organization_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('membership_id'),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_user')
    )
    op.create_index('idx_org_members_org', 'organization_members', ['organization_id'], unique=False)
    op.create_index('idx_org_members_user', 'organization_members', ['user_id'], unique=False)
    op.create_index('idx_org_members_role', 'organization_members', ['role'], unique=False)
    op.create_index(op.f('ix_organization_members_membership_id'), 'organization_members', ['membership_id'], unique=False)

    # Create organization_trading_accounts table
    op.create_table(
        'organization_trading_accounts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.BigInteger(), nullable=False),
        sa.Column('trading_account_id', sa.BigInteger(), nullable=False),
        sa.Column('default_permissions', sa.dialects.postgresql.JSONB(), nullable=False, server_default='["read"]'),
        sa.Column('added_by', sa.BigInteger(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('removed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.organization_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trading_account_id'], ['trading_accounts.trading_account_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['added_by'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'trading_account_id', name='uq_org_trading_account')
    )
    op.create_index('idx_org_accounts_org', 'organization_trading_accounts', ['organization_id'], unique=False)
    op.create_index('idx_org_accounts_account', 'organization_trading_accounts', ['trading_account_id'], unique=False)
    op.create_index(op.f('ix_organization_trading_accounts_id'), 'organization_trading_accounts', ['id'], unique=False)

    # Create organization_invitations table
    op.create_table(
        'organization_invitations',
        sa.Column('invitation_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.BigInteger(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('invited_role', sa.Enum('OWNER', 'ADMIN', 'MEMBER', 'VIEWER', name='organizationmemberrole'), nullable=False),
        sa.Column('custom_permissions', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('invitation_token', sa.String(length=255), nullable=False),
        sa.Column('invited_by', sa.BigInteger(), nullable=False),
        sa.Column('invited_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('accepted_by_user_id', sa.BigInteger(), nullable=True),
        sa.Column('rejected_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.organization_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['accepted_by_user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('invitation_id')
    )
    op.create_index('idx_org_invitations_org', 'organization_invitations', ['organization_id'], unique=False)
    op.create_index('idx_org_invitations_email', 'organization_invitations', ['email'], unique=False)
    op.create_index('idx_org_invitations_token', 'organization_invitations', ['invitation_token'], unique=False)
    op.create_index('idx_org_invitations_status', 'organization_invitations', ['status'], unique=False)
    op.create_index(op.f('ix_organization_invitations_email'), 'organization_invitations', ['email'], unique=False)
    op.create_index(op.f('ix_organization_invitations_invitation_id'), 'organization_invitations', ['invitation_id'], unique=False)
    op.create_index(op.f('ix_organization_invitations_invitation_token'), 'organization_invitations', ['invitation_token'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_organization_invitations_invitation_token'), table_name='organization_invitations')
    op.drop_index(op.f('ix_organization_invitations_invitation_id'), table_name='organization_invitations')
    op.drop_index(op.f('ix_organization_invitations_email'), table_name='organization_invitations')
    op.drop_index('idx_org_invitations_status', table_name='organization_invitations')
    op.drop_index('idx_org_invitations_token', table_name='organization_invitations')
    op.drop_index('idx_org_invitations_email', table_name='organization_invitations')
    op.drop_index('idx_org_invitations_org', table_name='organization_invitations')
    op.drop_table('organization_invitations')

    op.drop_index(op.f('ix_organization_trading_accounts_id'), table_name='organization_trading_accounts')
    op.drop_index('idx_org_accounts_account', table_name='organization_trading_accounts')
    op.drop_index('idx_org_accounts_org', table_name='organization_trading_accounts')
    op.drop_table('organization_trading_accounts')

    op.drop_index(op.f('ix_organization_members_membership_id'), table_name='organization_members')
    op.drop_index('idx_org_members_role', table_name='organization_members')
    op.drop_index('idx_org_members_user', table_name='organization_members')
    op.drop_index('idx_org_members_org', table_name='organization_members')
    op.drop_table('organization_members')

    op.drop_index(op.f('ix_organizations_slug'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_organization_id'), table_name='organizations')
    op.drop_index('idx_organizations_created_by', table_name='organizations')
    op.drop_index('idx_organizations_status', table_name='organizations')
    op.drop_index('idx_organizations_slug', table_name='organizations')
    op.drop_table('organizations')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS organizationmemberrole')
    op.execute('DROP TYPE IF EXISTS organizationstatus')
